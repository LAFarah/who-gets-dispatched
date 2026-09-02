from __future__ import annotations

import pandas as pd
import pytest

from ukpn.transform import (
    TECHNOLOGY_GROUPS, classify_technology, resolve_columns, settlement_period, tidy,
)
from tests.conftest import RAW_COLUMNS, raw_row


def _utc(*stamps: str) -> pd.Series:
    return pd.Series(pd.to_datetime(list(stamps), utc=True))


class TestSettlementPeriod:
    def test_first_period(self):
        assert settlement_period(_utc("2024-06-01T00:00:00+01:00")).iloc[0] == 1

    def test_ordinary_day_ends_at_48(self):
        assert settlement_period(_utc("2024-06-01T23:30:00+01:00")).iloc[0] == 48

    def test_spring_clock_change_ends_at_46(self):
        assert settlement_period(_utc("2024-03-31T22:30:00+00:00")).iloc[0] == 46

    def test_autumn_clock_change_ends_at_50(self):
        assert settlement_period(_utc("2024-10-27T23:30:00+00:00")).iloc[0] == 50

    def test_repeated_autumn_hour_is_distinguished(self):
        first = settlement_period(_utc("2024-10-27T00:30:00+00:00")).iloc[0]
        second = settlement_period(_utc("2024-10-27T01:30:00+00:00")).iloc[0]
        assert first != second


class TestClassifyTechnology:
    @pytest.mark.parametrize("value,expected", list(TECHNOLOGY_GROUPS.items()))
    def test_every_documented_category_maps(self, value, expected):
        assert classify_technology(value) == expected

    def test_unknown_is_not_silently_bucketed(self):
        assert classify_technology("Tidal Lagoon") == "unclassified"
        assert classify_technology(None) == "unclassified"


class TestResolveColumns:
    def test_accepts_the_real_schema(self, raw_frame):
        resolved = resolve_columns(raw_frame)
        assert resolved["company"] == "company_name"
        assert resolved["utilisation_mwh"] == "utilisation_mwh_req"

    def test_schema_change_fails_loudly(self, raw_frame):
        renamed = raw_frame.rename(columns={"utilisation_mwh_req": "util_mwh"})
        with pytest.raises(KeyError, match="utilisation_mwh_req"):
            resolve_columns(renamed)


class TestTidy:
    def test_sample_row_survives(self, raw_frame):
        out = tidy(raw_frame)
        assert len(out) == 1
        assert out["company"].iloc[0] == "Ohme"
        assert out["tech_group"].iloc[0] == "domestic_dsr"
        assert out["direction"].iloc[0] == "reduce"

    def test_documented_mwh_ties_to_mw_times_hours(self, raw_frame):
        out = tidy(raw_frame)
        derived = out["utilisation_mw"].iloc[0] * out["hours_requested"].iloc[0]
        assert abs(out["utilisation_mwh"].iloc[0] - derived) < 0.011

    def test_value_uses_utilisation_price(self, raw_frame):
        out = tidy(raw_frame)
        assert round(out["utilisation_value_gbp"].iloc[0], 3) == round(0.2 * 19.16, 3)
        assert out["availability_value_gbp"].iloc[0] == 0.0

    def test_bidirectional_types_map_to_increase(self):
        rows = [
            raw_row(dispatch_type="demand_turn_up"),
            raw_row(dispatch_type="generation_turn_down"),
        ]
        out = tidy(pd.DataFrame(rows, columns=RAW_COLUMNS))
        assert set(out["direction"]) == {"increase"}

    def test_row_key_is_built_from_the_composite(self, raw_frame):
        out = tidy(raw_frame)
        key = out["row_key"].iloc[0]
        assert "Ohme" in key and "Peak Reduction" in key
