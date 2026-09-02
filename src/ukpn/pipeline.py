"""End to end: extract -> tidy -> validate -> analyse -> figures.

    python -m ukpn.pipeline
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ukpn import analyse, extract, figures, transform, validate

log = logging.getLogger(__name__)

PROCESSED = Path("data/processed")


def run(refresh: bool = True) -> dict[str, pd.DataFrame]:
    PROCESSED.mkdir(parents=True, exist_ok=True)

    if refresh:
        extract.download()

    raw = extract.load_raw()
    before = len(raw)

    tidy = transform.tidy(raw)
    # Reconciliation assertion: the transform must not silently gain or lose rows.
    assert len(tidy) == before, f"Row count changed in transform: {before} -> {len(tidy)}"

    validated = validate.run_checks(tidy)
    summary = validate.summarise(validated)
    exc = validate.exceptions(validated)

    share = analyse.share_over_time(tidy)
    prices = analyse.price_by_group(tidy)
    zones = analyse.zone_concentration(tidy)
    companies = analyse.company_league(tidy)
    directions = analyse.direction_over_time(tidy)
    products = analyse.product_mix(tidy)

    for name, frame in [
        ("tidy", tidy), ("validation_summary", summary), ("exceptions", exc),
        ("share_over_time", share), ("price_by_group", prices),
        ("zone_concentration", zones), ("company_league", companies),
        ("direction_over_time", directions), ("product_mix", products),
    ]:
        frame.to_parquet(PROCESSED / f"{name}.parquet", index=False)

    figures.exceptions_chart(summary, total_rows=len(tidy))
    figures.share_chart(share)
    figures.price_chart(prices)

    log.info("Done. %s exceptions from %s dispatches.", len(exc), len(tidy))
    return {
        "tidy": tidy, "summary": summary, "exceptions": exc,
        "share": share, "prices": prices, "zones": zones,
        "companies": companies, "directions": directions, "products": products,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run()
