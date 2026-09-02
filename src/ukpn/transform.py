"""Normalise the raw dispatch export into a tidy analysis frame.

Column names verified against the live UKPN schema (see docs/schema.txt).

Two things about this dataset drive most of the design:

* There is **no dispatch identifier**. Rows are identified by the composite of
  company, flexible unit, start time and product.
* Availability and utilisation are **separate services with separate prices**.
  A dispatch can carry one, the other, or both. Collapsing them into a single
  "price" throws away the distinction UKPN are actually paying on.
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

LONDON = "Europe/London"

# Verified field names -> canonical names used downstream.
COLUMN_MAP: dict[str, str] = {
    "company_name": "company",
    "fu_id": "unit_id",
    "zone": "zone",
    "product": "product",
    "technology": "technology",
    "dispatch_type": "dispatch_type",
    "dispatch_method": "dispatch_method",
    "start_time_utc": "start_time",
    "end_time_utc": "end_time",
    "start_time_local": "start_time_local",
    "end_time_local": "end_time_local",
    "hours_requested": "hours_requested",
    "availability_mw_req": "availability_mw",
    "availability_mwh_req": "availability_mwh",
    "availability_price": "availability_price",
    "utilisation_mw_req": "utilisation_mw",
    "utilisation_mwh_req": "utilisation_mwh",
    "utilisation_price": "utilisation_price",
}

# The composite that stands in for a missing primary key.
KEY_COLUMNS = ["company", "unit_id", "start_time", "product"]

# UKPN report technology using the Energy Source categories from Licence
# Condition 31E. Grouping them is an editorial choice, so it is stated explicitly
# rather than inferred by keyword. Anything unlisted becomes "unclassified" and is
# reported as such -- never silently bucketed.
TECHNOLOGY_GROUPS: dict[str, str] = {
    # domestic / behind-the-meter demand
    "EV Charger DSR": "domestic_dsr",
    "Air Source Heat Pump": "domestic_dsr",
    "Ground Source Heat Pump": "domestic_dsr",
    # commercial and industrial demand
    "Flexible Site Demand": "ci_demand",
    "Demand": "ci_demand",
    # storage
    "On Site Battery": "behind_meter_storage",
    "Battery": "grid_scale_storage",
    "Stored Energy (all stored energy irrespective of the original energy source)": "grid_scale_storage",
    # generation
    "Engine": "generation",
    "Gas Turbine": "generation",
    "Fossil - Gas": "generation",
    "Biofuel - Landfill gas": "generation",
    "Onshore Wind Turbines": "generation",
    "Wind": "generation",
    "Photovoltaic": "generation",
    "Solar": "generation",
    "Other": "other",
}

# Two naming conventions appear in the record. Which one a row uses is itself a
# signal about when it was published -- see the vocabulary analysis in the README.
LC31E_VOCABULARY = {
    "Stored Energy (all stored energy irrespective of the original energy source)",
    "Demand", "Fossil - Gas", "Biofuel - Landfill gas", "Wind", "Solar",
    "Ground Source Heat Pump",
}

# Aggregators whose fleets are households rather than sites. Used for the
# "who dispatches domestic flexibility" cut. Verify against company_name values
# in the full extract before relying on it.
DOMESTIC_AGGREGATORS = {
    "Octopus", "Axle Energy Limited", "OVO Energy", "Ohme",
    "Ev.energy", "Electric Miles Ltd", "Fuse Energy",
}


def resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map source columns onto canonical names, failing loudly on a schema change."""
    lookup = {c.lower().strip().lstrip("\ufeff"): c for c in df.columns}
    resolved: dict[str, str] = {}
    missing: list[str] = []

    for source, canonical in COLUMN_MAP.items():
        actual = lookup.get(source.lower())
        if actual is None:
            missing.append(source)
        else:
            resolved[canonical] = actual

    if missing:
        raise KeyError(
            "UKPN schema has changed. Missing: " + ", ".join(missing)
            + f"\nActual columns: {list(df.columns)}"
        )
    return resolved


def classify_technology(value: object) -> str:
    """Explicit lookup. An unrecognised category stays unclassified by design."""
    if not isinstance(value, str):
        return "unclassified"
    return TECHNOLOGY_GROUPS.get(value.strip(), "unclassified")


def settlement_period(ts: pd.Series) -> pd.Series:
    """Half-hourly settlement period from a tz-aware timestamp.

    Computed from local midnight rather than a fixed 48-per-day assumption, so
    31 March yields 46 periods and 27 October yields 50.
    """
    local = ts.dt.tz_convert(LONDON)
    elapsed = (local - local.dt.normalize()).dt.total_seconds()
    return (elapsed // 1800).astype("Int64") + 1


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    cols = resolve_columns(df)
    out = pd.DataFrame(index=df.index)
    for canonical, source in cols.items():
        out[canonical] = df[source]

    # start_time_utc / end_time_utc are published as text, not datetime -- parse both
    # the UTC and local variants so they can be checked against each other.
    for col in ("start_time", "end_time", "start_time_local", "end_time_local"):
        out[col] = pd.to_datetime(out[col], errors="coerce", utc=True)

    numeric = [
        "hours_requested",
        "availability_mw", "availability_mwh", "availability_price",
        "utilisation_mw", "utilisation_mwh", "utilisation_price",
    ]
    for col in numeric:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["duration_hours"] = (out["end_time"] - out["start_time"]).dt.total_seconds() / 3600
    out["settlement_date"] = out["start_time"].dt.tz_convert(LONDON).dt.date
    out["settlement_period"] = settlement_period(out["start_time"])
    out["month"] = out["start_time"].dt.tz_convert(LONDON).dt.tz_localize(None).values.astype("datetime64[M]")

    # Requested value, split by service. UKPN state that requested volumes may not
    # match delivered volumes -- performance against baseline decides what is paid,
    # and outturn is published separately in the annual Flexibility Report.
    out["availability_value_gbp"] = out["availability_mwh"] * out["availability_price"]
    out["utilisation_value_gbp"] = out["utilisation_mwh"] * out["utilisation_price"]
    out["total_value_gbp"] = (
        out["availability_value_gbp"].fillna(0) + out["utilisation_value_gbp"].fillna(0)
    )
    out["requested_mwh"] = out["utilisation_mwh"].fillna(0)

    out["tech_group"] = out["technology"].map(classify_technology)
    out["technology_vocabulary"] = out["technology"].apply(
        lambda t: "lc31e" if t in LC31E_VOCABULARY else "descriptive"
    )
    out["is_domestic_aggregator"] = out["company"].isin(DOMESTIC_AGGREGATORS)

    # Bi-directional flexibility (demand_turn_up / generation_turn_down) went live
    # in April 2026, so this flag partitions old behaviour from new.
    out["direction"] = out["dispatch_type"].map(
        {
            "demand_turn_down": "reduce",
            "generation_turn_up": "reduce",
            "demand_turn_up": "increase",
            "generation_turn_down": "increase",
        }
    ).fillna("unknown")

    out["row_key"] = (
        out["company"].astype(str) + "|" + out["unit_id"].astype(str) + "|"
        + out["start_time"].astype(str) + "|" + out["product"].astype(str)
    )

    log.info(
        "Tidied %s dispatches across %s companies, %s zones, %s technologies",
        len(out), out["company"].nunique(), out["zone"].nunique(),
        out["technology"].nunique(),
    )
    unclassified = (out.tech_group == "unclassified").sum()
    if unclassified:
        log.warning(
            "%s rows have a technology not in TECHNOLOGY_GROUPS: %s",
            unclassified,
            sorted(out.loc[out.tech_group == "unclassified", "technology"].dropna().unique()),
        )
    return out
