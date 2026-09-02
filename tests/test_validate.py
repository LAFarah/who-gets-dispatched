from __future__ import annotations

import pandas as pd

from ukpn.transform import tidy
from ukpn.validate import CHECKS, exceptions, run_checks, summarise
from tests.conftest import RAW_COLUMNS, raw_row


def _checked(*rows: dict) -> pd.DataFrame:
    return run_checks(tidy(pd.DataFrame(list(rows), columns=RAW_COLUMNS)))


def test_documented_sample_row_is_clean():
    """The row UKPN publish as an example must pass every check.

    If this ever fails, either their data changed or a check is wrong -- and it is
    far more likely to be the check.
    """
    out = _checked(raw_row())
    assert out["n_flags"].iloc[0] == 0, out[list(CHECKS)].iloc[0][lambda s: s].index.tolist()


def test_mwh_inconsistent_with_mw_times_hours_is_flagged():
    out = _checked(raw_row(utilisation_mwh_req=5.0))  # 0.01 MW x 20h should be 0.2
    assert out["utilisation_mwh_mismatch"].iloc[0]


def test_hours_inconsistent_with_timestamps_is_flagged():
    out = _checked(raw_row(hours_requested=3.0))  # window is actually 20 hours
    assert out["hours_mismatch"].iloc[0]


def test_duplicate_composite_key_is_flagged():
    out = _checked(raw_row(), raw_row())
    assert out["duplicate_row_key"].all()


def test_differing_product_is_not_a_duplicate():
    out = _checked(raw_row(), raw_row(product="Day-Ahead"))
    assert not out["duplicate_row_key"].any()


def test_unit_id_equal_to_zone_is_flagged():
    out = _checked(raw_row(fu_id="Cobham", zone="Cobham"))
    assert out["unit_id_equals_zone"].iloc[0]


def test_no_volume_requested_is_flagged():
    out = _checked(raw_row(utilisation_mw_req=0.0, utilisation_mwh_req=0.0))
    assert out["no_volume_requested"].iloc[0]


def test_priced_with_no_volume_is_flagged():
    out = _checked(
        raw_row(utilisation_mw_req=0.0, utilisation_mwh_req=0.0, utilisation_price=50.0)
    )
    assert out["priced_but_no_volume"].iloc[0]


def test_volume_at_zero_price_is_flagged():
    out = _checked(raw_row(utilisation_price=0.0))
    assert out["volume_but_unpriced"].iloc[0]


def test_undocumented_technology_is_flagged():
    out = _checked(raw_row(technology="Tidal Lagoon"))
    assert out["unclassified_technology"].iloc[0]


def test_reversed_timestamps_are_flagged():
    out = _checked(
        raw_row(
            start_time_utc="2025-01-08 23:00:00+00:00",
            end_time_utc="2025-01-08 03:00:00+00:00",
        )
    )
    assert out["non_positive_duration"].iloc[0]


def test_summary_reports_every_check():
    summary = summarise(_checked(raw_row()))
    assert set(summary["check"]) == set(CHECKS)
    assert (summary["rows_flagged"] == 0).all()


def test_exceptions_returns_only_flagged_rows():
    # Different start time, so the composite key check does not also fire.
    out = _checked(
        raw_row(),
        raw_row(
            technology="Tidal Lagoon",
            start_time_utc="2025-01-09 03:00:00+00:00",
            end_time_utc="2025-01-09 23:00:00+00:00",
            start_time_local="2025-01-09T03:00:00+00:00",
            end_time_local="2025-01-09T23:00:00+00:00",
        ),
    )
    exc = exceptions(out)
    assert len(exc) == 1
    assert exc["technology"].iloc[0] == "Tidal Lagoon"


def test_same_unit_same_slot_different_technology_is_still_a_duplicate():
    """The composite key deliberately excludes technology: one unit cannot be
    dispatched twice for the same product in the same window."""
    out = _checked(raw_row(), raw_row(technology="Battery"))
    assert out["duplicate_row_key"].all()
