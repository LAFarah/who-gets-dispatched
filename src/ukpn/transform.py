"""Turn the raw dispatch export into a tidy dataframe for analysis.

Column names come from the live schema (docs/schema.txt).

Two things to know about this data:
- there's no dispatch ID, so a row is identified by company + unit + start time + product
- availability and utilisation are priced separately and a dispatch can have
  either or both, so they're kept as separate columns
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

LONDON = "Europe/London"

# UKPN field name -> name used in the rest of the code
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

# No dispatch ID in the data, so use these together as the key
KEY_COLUMNS = ["company", "unit_id", "start_time", "product"]

# UKPN's technology labels (mostly the Licence Condition 31E energy source
# categories) mapped to my own groups. Anything not listed ends up as
# "unclassified" so new labels show up in the logs.
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

# The technology field mixes two naming styles (e.g. "Battery" vs "Stored Energy
# (...)"). Tagging which one a row uses so I can check whether it changes over
# time or by provider (see the notebook).
LC31E_VOCABULARY = {
    "Stored Energy (all stored energy irrespective of the original energy source)",
    "Demand", "Fossil - Gas", "Biofuel - Landfill gas", "Wind", "Solar",
    "Ground Source Heat Pump",
}

# Providers whose portfolios are mainly households. TODO: check this list
# against all company names in the full extract.
DOMESTIC_AGGREGATORS = {
    "Octopus", "Axle Energy Limited", "OVO Energy", "Ohme",
    "Ev.energy", "Electric Miles Ltd", "Fuse Energy",
}


def resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """Match the raw columns to COLUMN_MAP. Raises if any are missing."""
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
    """Look up the technology group, or "unclassified" if it isn't mapped."""
    if not isinstance(value, str):
        return "unclassified"
    return TECHNOLOGY_GROUPS.get(value.strip(), "unclassified")


def settlement_period(ts: pd.Series) -> pd.Series:
    """Settlement period (1-based, half-hourly) from a tz-aware timestamp.

    Counted from local midnight so clock-change days come out with 46 or 50
    periods.
    """
    local = ts.dt.tz_convert(LONDON)
    elapsed = (local - local.dt.normalize()).dt.total_seconds()
    return (elapsed // 1800).astype("Int64") + 1


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    cols = resolve_columns(df)
    out = pd.DataFrame(index=df.index)
    for canonical, source in cols.items():
        out[canonical] = df[source]

    # Times come through as text. Parse the local ones too so validate.py can
    # compare them with UTC.
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

    # Value of what was requested. Delivered volumes (and what was actually paid)
    # are in UKPN's annual Flexibility Report, not this dataset.
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

    # Direction relative to load on the network: reduce = less net demand
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
