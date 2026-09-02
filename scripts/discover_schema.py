"""Step one. Run this before anything else.

Prints the real field names, types and descriptions, plus the distinct values of the
low-cardinality columns. Every mapping in src/ukpn/transform.py should be justified by
this output -- do not guess column names.

    python scripts/discover_schema.py > docs/schema.txt
"""

from __future__ import annotations

import collections
import logging
import sys

from ukpn.client import UKPNClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> int:
    client = UKPNClient()

    print("=" * 70)
    print("FIELDS")
    print("=" * 70)
    fields = client.fields()
    for f in fields:
        print(f"{f['name']:<32} {f['type']:<12} {f['label']}")
        if f["description"]:
            print(f"{'':<32} -- {f['description'][:110]}")

    print()
    print("=" * 70)
    print("SAMPLE ROW")
    print("=" * 70)
    sample = list(client.fetch_records(limit=1))
    if sample:
        for k, v in sample[0].items():
            print(f"{k:<32} {v!r}")

    print()
    print("=" * 70)
    print("DISTINCT VALUES (first 2,000 rows, text columns only)")
    print("=" * 70)
    text_cols = [f["name"] for f in fields if f["type"] in ("text", "string")]
    counters: dict[str, collections.Counter] = {c: collections.Counter() for c in text_cols}
    for row in client.fetch_records(limit=2000):
        for c in text_cols:
            if row.get(c) is not None:
                counters[c][row[c]] += 1

    for col, counter in counters.items():
        if 0 < len(counter) <= 40:
            print(f"\n{col}  ({len(counter)} distinct)")
            for value, n in counter.most_common():
                print(f"    {n:>6}  {value}")
        elif counter:
            print(f"\n{col}  ({len(counter)} distinct -- high cardinality, top 5)")
            for value, n in counter.most_common(5):
                print(f"    {n:>6}  {value}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
