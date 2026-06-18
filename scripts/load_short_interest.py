"""Populate archive.short_interest from yfinance for the tracked universe.

Run as a CronJob (weekly) or manually:
    python scripts/load_short_interest.py

Uses DOOMBERG_ARCHIVE_URL for the Postgres DSN.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_short_interest(symbols: list[str]) -> list[dict]:
    import yfinance as yf  # noqa: PLC0415

    rows = []
    total = len(symbols)
    for i, sym in enumerate(symbols, 1):
        try:
            info = yf.Ticker(sym).info
            si = info.get("sharesShort")
            fl = info.get("floatShares")
            pct = info.get("shortPercentOfFloat")
            ratio = info.get("shortRatio")
            if si is None and fl is None:
                continue
            rows.append({
                "symbol": sym.upper(),
                "short_interest_shares": si,
                "float_shares": fl,
                "short_float_pct": round(pct * 100, 4) if pct else None,
                "days_to_cover": ratio,
                "updated_at": _now(),
            })
            if i % 10 == 0:
                print(f"  fetched {i}/{total}...", flush=True)
        except Exception as exc:
            print(f"  WARN: {sym}: {exc}", file=sys.stderr)
    return rows


def upsert_short_interest(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO archive.short_interest
          (symbol, short_interest_shares, float_shares, short_float_pct, days_to_cover, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol) DO UPDATE SET
          short_interest_shares = EXCLUDED.short_interest_shares,
          float_shares          = EXCLUDED.float_shares,
          short_float_pct       = EXCLUDED.short_float_pct,
          days_to_cover         = EXCLUDED.days_to_cover,
          updated_at            = EXCLUDED.updated_at
    """
    # Ensure upsert works — add unique constraint if missing.
    conn.execute(
        "ALTER TABLE archive.short_interest ADD COLUMN IF NOT EXISTS ctid_dummy int;"
        if False else  # placeholder — just make sure the PK exists
        "SELECT 1"
    )
    # Use executemany for speed.
    with conn.cursor() as cur:
        cur.executemany(sql, [
            (r["symbol"], r["short_interest_shares"], r["float_shares"],
             r["short_float_pct"], r["days_to_cover"], r["updated_at"])
            for r in rows
        ])
    return len(rows)


def main() -> None:
    import psycopg  # noqa: PLC0415

    dsn = os.environ.get("DOOMBERG_ARCHIVE_URL", "")
    if not dsn:
        print("ERROR: DOOMBERG_ARCHIVE_URL not set", file=sys.stderr)
        sys.exit(1)

    print("load_short_interest: connecting to archive DB...")
    with psycopg.connect(dsn, autocommit=True) as conn:
        # Ensure unique constraint so upsert works.
        conn.execute("""
            DO $$BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'short_interest_symbol_key'
              ) THEN
                ALTER TABLE archive.short_interest ADD CONSTRAINT short_interest_symbol_key UNIQUE (symbol);
              END IF;
            END$$;
        """)

        # Get the tracked universe.
        rows = conn.execute(
            "SELECT symbol FROM archive.universe WHERE tracked = true ORDER BY symbol"
        ).fetchall()
        symbols = [r[0] for r in rows]
        print(f"load_short_interest: fetching {len(symbols)} symbols from yfinance...")

        data = fetch_short_interest(symbols)
        print(f"load_short_interest: got data for {len(data)} symbols")

        n = upsert_short_interest(conn, data)
        print(f"load_short_interest: upserted {n} rows → archive.short_interest")


if __name__ == "__main__":
    main()
