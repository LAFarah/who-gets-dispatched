"""Streamlit app for exploring the processed dispatch data."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ukpn import analyse, validate

st.set_page_config(page_title="Who gets dispatched?", layout="wide")


@st.cache_data(show_spinner="Loading dispatches...")
def load() -> pd.DataFrame:
    # The raw CSV is gitignored so it won't be there when deployed. Use the
    # tidied parquet from the pipeline instead.
    return pd.read_parquet("data/processed/tidy.parquet")


@st.cache_data(show_spinner="Running checks...")
def checked(df: pd.DataFrame) -> pd.DataFrame:
    return validate.run_checks(df)


st.title("Who gets dispatched?")
st.caption(
    "UK Power Networks flexibility dispatches, April 2023 onwards. Volumes and values "
    "are requested, not delivered. The data quality checks are still a work in "
    "progress and some of them over-flag."
)

try:
    df = load()
except FileNotFoundError as e:
    st.error(f"{e}\n\nRun `python -m ukpn.pipeline` first.")
    st.stop()

val = checked(df)

with st.sidebar:
    st.header("Filter")
    pick_company = st.multiselect("Provider", sorted(df["company"].dropna().unique()))
    pick_product = st.multiselect("Product", sorted(df["product"].dropna().unique()))
    pick_tech = st.multiselect("Technology group", sorted(df["tech_group"].dropna().unique()))

mask = pd.Series(True, index=df.index)
if pick_company:
    mask &= df["company"].isin(pick_company)
if pick_product:
    mask &= df["product"].isin(pick_product)
if pick_tech:
    mask &= df["tech_group"].isin(pick_tech)
d = df[mask]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Dispatches", f"{len(d):,}")
c2.metric("Utilisation MWh", f"{d['utilisation_mwh'].sum():,.1f}")
c3.metric("Requested value", f"£{d['total_value_gbp'].sum():,.0f}")
dom = d.loc[d.tech_group == "domestic_dsr", "utilisation_mwh"].sum()
c4.metric("Domestic DSR share", f"{100 * dom / max(d['utilisation_mwh'].sum(), 1e-9):.1f}%")
c5.metric("Rows flagged", f"{int(val.loc[mask, 'n_flags'].gt(0).sum()):,}")

tabs = st.tabs(["Share over time", "Providers", "Price", "Zones", "Direction", "Products", "Exceptions"])

with tabs[0]:
    share = analyse.share_over_time(d)
    st.line_chart(
        share.pivot(index="period", columns="tech_group", values="share_of_mwh") * 100,
        y_label="% of requested MWh",
    )
    st.dataframe(share, use_container_width=True, hide_index=True)

with tabs[1]:
    st.caption("Provider names are published by UKPN in this dataset.")
    st.dataframe(analyse.company_league(d), use_container_width=True, hide_index=True)

with tabs[2]:
    st.dataframe(analyse.price_by_group(d), use_container_width=True, hide_index=True)
    st.caption(
        "Prices are volume-weighted. EV charger dispatches are frequent and small, "
        "so a simple average would mostly reflect them."
    )

with tabs[3]:
    st.dataframe(analyse.zone_concentration(d), use_container_width=True, hide_index=True)

with tabs[4]:
    st.caption("Dispatches per month by dispatch type.")
    dirs = analyse.direction_over_time(d)
    st.bar_chart(dirs.pivot(index="period", columns="dispatch_type", values="dispatches"))
    st.dataframe(dirs, use_container_width=True, hide_index=True)

with tabs[5]:
    st.dataframe(analyse.product_mix(d), use_container_width=True, hide_index=True)

with tabs[6]:
    st.subheader("Flagged rows")
    st.caption(
        "UKPN's published QC checks where the public data allows, plus some "
        "consistency checks of my own. Flagged rows need a closer look; they aren't "
        "necessarily wrong."
    )
    summary = validate.summarise(val.loc[mask])
    st.bar_chart(summary.set_index("check")["rows_flagged"])
    st.dataframe(summary, use_container_width=True, hide_index=True)

    exc = validate.exceptions(val.loc[mask])
    st.write(f"**{len(exc):,}** of **{len(d):,}** dispatches flagged "
             f"({100 * len(exc) / max(len(d), 1):.3f}%)")
    st.dataframe(exc, use_container_width=True, hide_index=True)
    st.download_button("Download exceptions (CSV)", exc.to_csv(index=False),
                       "exceptions.csv", "text/csv")
