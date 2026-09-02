"""Publication figures. The exceptions chart is the one that goes in the README."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ukpn.validate import CHECKS

FIG_DIR = Path("figures")

INK = "#1a1a1a"
MUTED = "#8a8a8a"
FLAG = "#c1440e"
CLEAN = "#d8d8d8"
DIST = "#0b6e4f"
GRID = "#2b4570"


def _style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=INK, labelsize=9)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.8)
    ax.set_axisbelow(True)


def exceptions_chart(summary: pd.DataFrame, total_rows: int, out: Path | None = None) -> Path:
    """Horizontal bars: rows flagged per check, against the size of the dataset.

    Designed so the honest headline is unavoidable -- the annotation states how many
    rows out of how many, so a small number reads as a small number.
    """
    out = out or FIG_DIR / "exceptions_by_check.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    data = summary.sort_values("rows_flagged")
    fig, ax = plt.subplots(figsize=(9, 0.52 * len(data) + 2.2))

    colours = [FLAG if n > 0 else CLEAN for n in data["rows_flagged"]]
    bars = ax.barh(data["check"].str.replace("_", " "), data["rows_flagged"], color=colours, height=0.62)

    for bar, n, pct in zip(bars, data["rows_flagged"], data["pct_of_total"]):
        if n == 0:
            ax.text(0.4, bar.get_y() + bar.get_height() / 2, "0", va="center",
                    ha="left", fontsize=9, color=MUTED)
        else:
            ax.text(bar.get_width() * 1.02, bar.get_y() + bar.get_height() / 2,
                    f"{n:,}  ({pct:.2f}%)", va="center", ha="left", fontsize=9, color=INK)

    flagged = int(summary["rows_flagged"].gt(0).any() and summary["rows_flagged"].sum())
    ax.set_title(
        "Rows flagged by UKPN's own published QC criteria, reproduced independently",
        fontsize=12, color=INK, pad=16, loc="left",
    )
    ax.set_xlabel(f"Dispatches flagged (of {total_rows:,} total, 1 Apr 2023 onwards)",
                  fontsize=9, color=MUTED)
    ax.set_ylabel("")
    ax.set_xlim(0, max(data["rows_flagged"].max() * 1.28, 1))
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def share_chart(share: pd.DataFrame, out: Path | None = None) -> Path:
    """The headline finding: distributed share of requested MWh over time."""
    out = out or FIG_DIR / "distributed_share.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    pivot = share.pivot(index="period", columns="tech_group", values="share_of_mwh").fillna(0)
    fig, ax = plt.subplots(figsize=(9, 4.6))

    palette = {
        "domestic_dsr": DIST, "grid_scale": GRID, "behind_meter_storage": "#7a5c99",
        "ci_demand": "#b08900", "other": CLEAN, "unclassified": "#cccccc",
    }
    for col, colour in palette.items():
        if col in pivot.columns:
            ax.plot(pivot.index, pivot[col] * 100, label=col.replace("_", "-"),
                    color=colour, linewidth=2.2, marker="o", markersize=4)

    ax.set_title("Share of requested flexibility volume by technology group",
                 fontsize=12, color=INK, pad=16, loc="left")
    ax.set_ylabel("% of requested MWh", fontsize=9, color=MUTED)
    ax.set_xlabel("")
    ax.legend(frameon=False, fontsize=9)
    _style(ax)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.8)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def price_chart(prices: pd.DataFrame, out: Path | None = None) -> Path:
    """Volume-weighted £/MWh by product, split by technology group."""
    out = out or FIG_DIR / "price_by_product.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    d = prices[prices.tech_group.isin(["domestic_dsr", "grid_scale"])]
    pivot = d.pivot(index="product", columns="tech_group", values="vw_price_gbp_per_mwh").fillna(0)

    fig, ax = plt.subplots(figsize=(9, 0.7 * len(pivot) + 2.2))
    y = range(len(pivot))
    height = 0.36
    if "domestic_dsr" in pivot:
        ax.barh([i + height / 2 for i in y], pivot["domestic_dsr"], height=height,
                color=DIST, label="domestic DSR")
    if "grid_scale" in pivot:
        ax.barh([i - height / 2 for i in y], pivot["grid_scale"], height=height,
                color=GRID, label="grid-scale")

    ax.set_yticks(list(y))
    ax.set_yticklabels(pivot.index, fontsize=9)
    ax.set_title("Volume-weighted price paid, by product and technology group",
                 fontsize=12, color=INK, pad=16, loc="left")
    ax.set_xlabel("£/MWh (requested volume weighted)", fontsize=9, color=MUTED)
    ax.legend(frameon=False, fontsize=9)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out
