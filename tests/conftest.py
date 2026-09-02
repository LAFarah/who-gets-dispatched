"""Fixtures built from the real UKPN schema (docs/schema.txt).

Every test row starts from the sample row UKPN publish in their own field
documentation, so if the tests ever fail against real data it means either the
schema changed or a check encodes a wrong assumption.
"""

from __future__ import annotations

import pandas as pd
import pytest

RAW_COLUMNS = [
    "company_name", "fu_id", "zone", "product", "start_time_local", "end_time_local",
    "availability_mw_req", "utilisation_mw_req", "availability_price", "utilisation_price",
    "availability_mwh_req", "utilisation_mwh_req", "technology", "dispatch_type",
    "hours_requested", "dispatch_method", "start_time_utc", "end_time_utc", "time_utc",
]


def raw_row(**overrides) -> dict:
    """The documented sample row, overridable field by field."""
    row = {
        "company_name": "Ohme",
        "fu_id": "OHME-CENT-SAOU-8573",
        "zone": "Cobham",
        "product": "Peak Reduction",
        "start_time_local": "2025-01-08T03:00:00+00:00",
        "end_time_local": "2025-01-08T23:00:00+00:00",
        "availability_mw_req": 0.0,
        "utilisation_mw_req": 0.01,
        "availability_price": 0.0,
        "utilisation_price": 19.16,
        "availability_mwh_req": 0.0,
        "utilisation_mwh_req": 0.2,
        "technology": "EV Charger DSR",
        "dispatch_type": "demand_turn_down",
        "hours_requested": 20.0,
        "dispatch_method": "epex",
        "start_time_utc": "2025-01-08 03:00:00+00:00",
        "end_time_utc": "2025-01-08 23:00:00+00:00",
        "time_utc": "03:00:00+00:00",
    }
    row.update(overrides)
    return row


@pytest.fixture
def raw_frame() -> pd.DataFrame:
    return pd.DataFrame([raw_row()], columns=RAW_COLUMNS)
