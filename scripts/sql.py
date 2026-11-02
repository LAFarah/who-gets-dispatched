"""SQL shell over the pipeline outputs, using DuckDB.

Each parquet file in data/processed becomes a view with the same name
(tidy.parquet -> tidy).

    python scripts/sql.py
    python scripts/sql.py "SELECT company, count(*) FROM tidy GROUP BY 1 ORDER BY 2 DESC"

In the shell: \\d lists tables, \\d <table> describes one, \\q quits.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

PROCESSED = Path("data/processed")

pd.set_option("display.max_columns", 200)
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 200)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")


def connect() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with a view per parquet file."""
    con = duckdb.connect()
    files = sorted(PROCESSED.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"No Parquet files in {PROCESSED}. Run: python -m ukpn.pipeline"
        )
    for f in files:
        con.execute(
            f'CREATE OR REPLACE VIEW "{f.stem}" AS '
            f"SELECT * FROM read_parquet('{f.as_posix()}')"
        )
    return con


def tables(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    rows = []
    for f in sorted(PROCESSED.glob("*.parquet")):
        n = con.execute(f'SELECT count(*) FROM "{f.stem}"').fetchone()[0]
        cols = con.execute(f'SELECT * FROM "{f.stem}" LIMIT 0').df().shape[1]
        rows.append({"table": f.stem, "rows": n, "columns": cols})
    return pd.DataFrame(rows)


def describe(con: duckdb.DuckDBPyConnection, table: str) -> pd.DataFrame:
    return con.execute(f'DESCRIBE "{table}"').df()


def repl() -> None:
    con = connect()
    print("DuckDB over data/processed. \\d for tables, \\q to quit.\n")
    print(tables(con).to_string(index=False))
    print()

    buffer: list[str] = []
    while True:
        prompt = "sql> " if not buffer else "...> "
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            return

        stripped = line.strip()
        if not buffer:
            if stripped in (r"\q", "exit", "quit"):
                return
            if stripped == r"\d":
                print(tables(con).to_string(index=False), "\n")
                continue
            if stripped.startswith(r"\d "):
                print(describe(con, stripped[3:].strip()).to_string(index=False), "\n")
                continue
            if not stripped:
                continue

        buffer.append(line)
        # Run on a closing semicolon. One-line selects run straight away.
        joined = "\n".join(buffer)
        one_liner = len(buffer) == 1 and stripped.lower().startswith(
            ("select", "with", "describe", "summarize", "pivot")
        )
        if not joined.rstrip().endswith(";") and not one_liner:
            continue

        query = joined.rstrip().rstrip(";")
        buffer = []
        try:
            print(con.execute(query).df().to_string(index=False), "\n")
        except Exception as exc:
            print(f"error: {exc}\n")


def main() -> int:
    if len(sys.argv) > 1:
        con = connect()
        print(con.execute(" ".join(sys.argv[1:])).df().to_string(index=False))
        return 0
    repl()
    return 0


if __name__ == "__main__":
    sys.exit(main())
