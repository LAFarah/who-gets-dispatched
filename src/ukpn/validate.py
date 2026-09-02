"""Reproduce UKPN's published quality-control criteria, plus internal consistency checks.

UKPN state that dispatches pass a QC algorithm checking that they are timed
consistently with the contracted service window, matched to the correct zone,
unique, issued at the contracted price and volume, and matched to an active contract.

Three of those need contract data the public feed does not carry. What follows are
the internally-verifiable analogues, plus checks the published schema makes possible.
A flagged row is a question about a field definition, not a proven error.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ukpn.transform import KEY_COLUMNS

log = logging.getLogger(__name__)

# Tolerance for float comparisons on MWh figures (they are published to 2dp).
TOL = 0.011

CHECKS: dict[str, str] = {
    "duplicate_row_key": "Same company, unit, start time and product appears more than once",
    "utilisation_mwh_mismatch": "utilisation_mwh_req does not equal utilisation_mw_req x hours_requested",
    "availability_mwh_mismatch": "availability_mwh_req does not equal availability_mw_req x hours_requested",
    "hours_mismatch": "hours_requested does not match end_time_utc minus start_time_utc",
    "utc_local_mismatch": "UTC and local timestamps do not describe the same instant",
    "unit_id_equals_zone": "Flexible unit identifier is identical to the zone name",
    "no_volume_requested": "Neither availability nor utilisation volume was requested",
    "priced_but_no_volume": "A price is set against zero requested volume",
    "volume_but_unpriced": "Volume requested at a price of zero",
    "non_positive_duration": "End time is at or before start time",
    "overlapping_window_same_unit": "Same flexible unit dispatched in overlapping windows",
    "unclassified_technology": "Technology value not present in the documented category list",
    "price_outlier_for_product": "Utilisation price far outside the usual range for its product",
}


def _close(a: pd.Series, b: pd.Series, tol: float = TOL) -> pd.Series:
    """True where the two differ by more than tol, ignoring rows where either is null."""
    both = a.notna() & b.notna()
    return both & ((a - b).abs() > tol)


def _price_outliers(df: pd.DataFrame, n_iqr: float = 3.0) -> pd.Series:
    """Per-product IQR band. Products are priced on different bases, so a single
    global band would flag the wrong rows."""
    flag = pd.Series(False, index=df.index)
    for _, grp in df.groupby("product", dropna=False):
        prices = grp["utilisation_price"].dropna()
        prices = prices[prices > 0]
        if len(prices) < 30:
            continue
        q1, q3 = prices.quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr <= 0:
            continue
        lo, hi = q1 - n_iqr * iqr, q3 + n_iqr * iqr
        flag.loc[grp.index] = (grp["utilisation_price"] < lo) | (grp["utilisation_price"] > hi)
    return flag.fillna(False)


def _overlapping_windows(df: pd.DataFrame) -> pd.Series:
    flag = pd.Series(False, index=df.index)
    ordered = df.sort_values(["unit_id", "start_time"])
    prev_end = ordered.groupby("unit_id")["end_time"].shift(1)
    overlap = (ordered["start_time"] < prev_end).fillna(False)
    flag.loc[ordered.index[overlap]] = True
    return flag


def run_checks(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["duplicate_row_key"] = out.duplicated(subset=KEY_COLUMNS, keep=False)

    out["utilisation_mwh_mismatch"] = _close(
        out["utilisation_mwh"], out["utilisation_mw"] * out["hours_requested"]
    )
    out["availability_mwh_mismatch"] = _close(
        out["availability_mwh"], out["availability_mw"] * out["hours_requested"]
    )
    out["hours_mismatch"] = _close(out["hours_requested"], out["duration_hours"], tol=0.02)

    out["utc_local_mismatch"] = (
        out["start_time"].notna() & out["start_time_local"].notna()
        & (out["start_time"] != out["start_time_local"])
    )

    out["unit_id_equals_zone"] = (
        out["unit_id"].astype(str).str.strip().str.casefold()
        == out["zone"].astype(str).str.strip().str.casefold()
    )

    avail = out["availability_mwh"].fillna(0)
    util = out["utilisation_mwh"].fillna(0)
    avail_p = out["availability_price"].fillna(0)
    util_p = out["utilisation_price"].fillna(0)

    out["no_volume_requested"] = (avail <= 0) & (util <= 0)
    out["priced_but_no_volume"] = ((avail <= 0) & (avail_p > 0)) | ((util <= 0) & (util_p > 0))
    out["volume_but_unpriced"] = ((avail > 0) & (avail_p <= 0)) | ((util > 0) & (util_p <= 0))

    out["non_positive_duration"] = out["duration_hours"].le(0).fillna(False)
    out["overlapping_window_same_unit"] = _overlapping_windows(out)
    out["unclassified_technology"] = out["tech_group"].eq("unclassified")
    out["price_outlier_for_product"] = _price_outliers(out)

    out["n_flags"] = out[list(CHECKS)].sum(axis=1)
    log.info(
        "Validation: %s of %s rows flagged by at least one check (%.3f%%)",
        (out.n_flags > 0).sum(), len(out), 100 * (out.n_flags > 0).mean(),
    )
    return out


def summarise(validated: pd.DataFrame) -> pd.DataFrame:
    total = len(validated)
    rows = [
        {
            "check": check,
            "description": description,
            "rows_flagged": int(validated[check].sum()),
            "pct_of_total": round(100 * float(validated[check].sum()) / total, 4) if total else 0.0,
        }
        for check, description in CHECKS.items()
    ]
    return pd.DataFrame(rows).sort_values("rows_flagged", ascending=False, ignore_index=True)


def exceptions(validated: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "company", "unit_id", "zone", "product", "technology", "tech_group",
        "dispatch_type", "start_time", "end_time", "hours_requested", "duration_hours",
        "availability_mw", "availability_mwh", "availability_price",
        "utilisation_mw", "utilisation_mwh", "utilisation_price", "n_flags",
    ] + list(CHECKS)
    present = [c for c in cols if c in validated.columns]
    return (
        validated.loc[validated.n_flags > 0, present]
        .sort_values(["n_flags", "start_time"], ascending=[False, True])
        .reset_index(drop=True)
    )
