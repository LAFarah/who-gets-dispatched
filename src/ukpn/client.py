"""Minimal client for the UK Power Networks Opendatasoft Explore API (v2.1).

UKPN publish an official client (`ukpyn` on PyPI). This is deliberately hand-rolled
so the pagination limits, export endpoint and auth behaviour are visible and testable
rather than hidden behind a dependency.

Two ways to read a dataset:

  * ``fetch_records``  -- paged /records endpoint. Convenient, but Opendatasoft caps
    offset paging at 10,000 rows, so it is only safe for exploration and filtered pulls.
  * ``export_dataset`` -- /exports/csv endpoint. No row cap. This is the correct way
    to pull the full dispatch history.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Iterator

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://ukpowernetworks.opendatasoft.com/api/explore/v2.1"
DATASET = "ukpn-flexibility-dispatches"

# Opendatasoft refuses offset paging beyond this point.
MAX_OFFSET = 10_000
PAGE_SIZE = 100


class UKPNClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout: int = 30,
        max_retries: int = 4,
    ) -> None:
        # The portal requires a login for some datasets. If you have a key, set
        # UKPN_API_KEY in the environment rather than committing it.
        self.api_key = api_key or os.environ.get("UKPN_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["Authorization"] = f"Apikey {self.api_key}"

    # ----- low level -------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        url = f"{self.base_url}{path}"
        backoff = 1.0
        for attempt in range(1, self.max_retries + 1):
            resp = self.session.get(url, params=params, timeout=self.timeout)

            if resp.status_code == 200:
                return resp

            if resp.status_code in (429, 500, 502, 503, 504):
                log.warning(
                    "HTTP %s from %s (attempt %s/%s), retrying in %.1fs",
                    resp.status_code, url, attempt, self.max_retries, backoff,
                )
                time.sleep(backoff)
                backoff *= 2
                continue

            if resp.status_code in (401, 403):
                raise PermissionError(
                    f"HTTP {resp.status_code} from UKPN. This dataset may require a "
                    "portal login. Set UKPN_API_KEY in your environment."
                )

            resp.raise_for_status()

        raise RuntimeError(f"Gave up on {url} after {self.max_retries} attempts")

    # ----- public ----------------------------------------------------------

    def dataset_info(self, dataset: str = DATASET) -> dict[str, Any]:
        """Metadata including the field list. Run this before writing any transform."""
        return self._get(f"/catalog/datasets/{dataset}").json()

    def fields(self, dataset: str = DATASET) -> list[dict[str, str]]:
        info = self.dataset_info(dataset)
        return [
            {
                "name": f.get("name", ""),
                "type": f.get("type", ""),
                "label": f.get("label", ""),
                "description": (f.get("description") or "").strip(),
            }
            for f in info.get("fields", [])
        ]

    def fetch_records(
        self,
        dataset: str = DATASET,
        where: str | None = None,
        select: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Page the /records endpoint. Stops at MAX_OFFSET -- see module docstring."""
        offset = 0
        yielded = 0
        while True:
            if offset >= MAX_OFFSET:
                log.warning(
                    "Reached the Opendatasoft offset ceiling (%s rows). "
                    "Use export_dataset() for the full history.", MAX_OFFSET,
                )
                return

            params: dict[str, Any] = {"limit": PAGE_SIZE, "offset": offset}
            if where:
                params["where"] = where
            if select:
                params["select"] = select
            if order_by:
                params["order_by"] = order_by

            payload = self._get(f"/catalog/datasets/{dataset}/records", params).json()
            results = payload.get("results", [])
            if not results:
                return

            for row in results:
                yield row
                yielded += 1
                if limit and yielded >= limit:
                    return

            offset += PAGE_SIZE

    def export_dataset(self, dataset: str = DATASET, fmt: str = "csv") -> bytes:
        """Full dataset export -- no row cap. Use this for the real pull."""
        resp = self._get(f"/catalog/datasets/{dataset}/exports/{fmt}")
        return resp.content
