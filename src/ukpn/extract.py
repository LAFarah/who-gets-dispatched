"""Pull the dispatch history to disk. Raw stays raw -- no transformation here."""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import pandas as pd

from ukpn.client import DATASET, UKPNClient

log = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")


def download(dataset: str = DATASET, raw_dir: Path = RAW_DIR) -> Path:
    """Export the full dataset to a date-stamped CSV. Re-runnable and idempotent."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().isoformat()
    path = raw_dir / f"{dataset}_{stamp}.csv"

    if path.exists():
        log.info("Already have %s, skipping download", path)
        return path

    client = UKPNClient()
    log.info("Exporting %s ...", dataset)
    content = client.export_dataset(dataset, fmt="csv")
    path.write_bytes(content)
    log.info("Wrote %s (%.1f MB)", path, len(content) / 1e6)
    return path


def latest_raw(raw_dir: Path = RAW_DIR, dataset: str = DATASET) -> Path:
    files = sorted(raw_dir.glob(f"{dataset}_*.csv"))
    if not files:
        raise FileNotFoundError(
            f"No raw extract in {raw_dir}. Run: python -m ukpn.extract"
        )
    return files[-1]


def load_raw(path: Path | None = None) -> pd.DataFrame:
    path = path or latest_raw()
    log.info("Reading %s", path)
    return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    download()
