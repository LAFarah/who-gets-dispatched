"""Summary tables used by the pipeline, the app and the charts."""

from __future__ import annotations

import pandas as pd


def share_over_time(df: pd.DataFrame, freq: str = "Q") -> pd.DataFrame:
    """Technology group share of dispatches and requested MWh, over time."""
    d = df.dropna(subset=["start_time"]).copy()
    d["period"] = d["start_time"].dt.tz_convert("Europe/London").dt.tz_localize(None).dt.to_period(freq).dt.to_timestamp()

    grouped = (
        d.groupby(["period", "tech_group"], dropna=False)
        .agg(
            dispatches=("row_key", "size"),
            utilisation_mwh=("utilisation_mwh", "sum"),
            value_gbp=("total_value_gbp", "sum"),
        )
        .reset_index()
    )
    totals = grouped.groupby("period")[["dispatches", "utilisation_mwh"]].transform("sum")
    grouped["share_of_dispatches"] = grouped["dispatches"] / totals["dispatches"]
    grouped["share_of_mwh"] = grouped["utilisation_mwh"] / totals["utilisation_mwh"]
    return grouped


def company_league(df: pd.DataFrame) -> pd.DataFrame:
    """One row per provider: dispatches, units, zones, volumes and prices."""
    d = df.copy()
    d["util_value"] = d["utilisation_mwh"].fillna(0) * d["utilisation_price"].fillna(0)

    out = (
        d.groupby("company")
        .agg(
            dispatches=("row_key", "size"),
            units=("unit_id", "nunique"),
            zones=("zone", "nunique"),
            products=("product", "nunique"),
            utilisation_mwh=("utilisation_mwh", "sum"),
            availability_mwh=("availability_mwh", "sum"),
            util_value_gbp=("util_value", "sum"),
            total_value_gbp=("total_value_gbp", "sum"),
            first_dispatch=("start_time", "min"),
            last_dispatch=("start_time", "max"),
            mean_hours=("hours_requested", "mean"),
        )
        .reset_index()
    )
    out["vw_util_price"] = out["util_value_gbp"] / out["utilisation_mwh"].replace(0, pd.NA)
    out["mwh_per_dispatch"] = out["utilisation_mwh"] / out["dispatches"]
    return out.sort_values("utilisation_mwh", ascending=False, ignore_index=True)


def price_by_group(df: pd.DataFrame) -> pd.DataFrame:
    """Volume-weighted utilisation price by product and technology group.

    Weighted by MWh because there are lots of tiny EV charger dispatches, which
    would drag a simple mean around.
    """
    d = df.dropna(subset=["utilisation_price", "utilisation_mwh"]).copy()
    d = d[d["utilisation_mwh"] > 0]
    d["value"] = d["utilisation_price"] * d["utilisation_mwh"]

    out = (
        d.groupby(["product", "tech_group"], dropna=False)
        .agg(
            dispatches=("row_key", "size"),
            utilisation_mwh=("utilisation_mwh", "sum"),
            value_gbp=("value", "sum"),
            median_price=("utilisation_price", "median"),
            mean_mwh_per_dispatch=("utilisation_mwh", "mean"),
        )
        .reset_index()
    )
    out["vw_price_gbp_per_mwh"] = out["value_gbp"] / out["utilisation_mwh"]
    return out.sort_values("utilisation_mwh", ascending=False, ignore_index=True)


def zone_concentration(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Top zones by volume, with provider count, domestic share and median price."""
    d = df.dropna(subset=["zone"]).copy()
    d["is_domestic"] = d["tech_group"].eq("domestic_dsr")
    d["domestic_mwh"] = d["utilisation_mwh"].where(d["is_domestic"], 0)

    out = (
        d.groupby("zone")
        .agg(
            dispatches=("row_key", "size"),
            companies=("company", "nunique"),
            units=("unit_id", "nunique"),
            utilisation_mwh=("utilisation_mwh", "sum"),
            domestic_mwh=("domestic_mwh", "sum"),
            median_util_price=("utilisation_price", "median"),
        )
        .reset_index()
    )
    out["domestic_share"] = out["domestic_mwh"] / out["utilisation_mwh"].replace(0, pd.NA)
    return out.sort_values("utilisation_mwh", ascending=False, ignore_index=True).head(top_n)


def direction_over_time(df: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
    """Dispatches and MWh per period, by dispatch type."""
    d = df.dropna(subset=["start_time"]).copy()
    d["period"] = d["start_time"].dt.tz_convert("Europe/London").dt.tz_localize(None).dt.to_period(freq).dt.to_timestamp()
    return (
        d.groupby(["period", "dispatch_type"], dropna=False)
        .agg(dispatches=("row_key", "size"), utilisation_mwh=("utilisation_mwh", "sum"))
        .reset_index()
    )


def product_mix(df: pd.DataFrame) -> pd.DataFrame:
    """Which products carry availability payments and which are utilisation-only."""
    d = df.copy()
    return (
        d.groupby("product")
        .agg(
            dispatches=("row_key", "size"),
            with_availability=("availability_mwh", lambda s: int((s.fillna(0) > 0).sum())),
            with_utilisation=("utilisation_mwh", lambda s: int((s.fillna(0) > 0).sum())),
            availability_value_gbp=("availability_value_gbp", "sum"),
            utilisation_value_gbp=("utilisation_value_gbp", "sum"),
            mean_hours=("hours_requested", "mean"),
        )
        .reset_index()
        .sort_values("dispatches", ascending=False, ignore_index=True)
    )
