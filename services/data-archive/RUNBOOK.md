# Runbook — load the v1 archive into Postgres

The v1 market-data archive (`data/v1_archive.json`, ~92 MB, **240,220 rows** across 15
tables) is loaded into Postgres schema `archive` by a single idempotent command. This is
READ-ONLY reference data for the data-layer skills; it lives in its own `archive` schema,
isolated from the v2 platform tables (runs/strategies/trace/books).

## One-command load

```bash
export DOOMBERG_ARCHIVE_URL=postgresql://user:pass@host:5432/dbname
uv run python scripts/import_v1_archive.py
```

The script:
1. `CREATE SCHEMA IF NOT EXISTS archive` + all 15 `archive.*` tables and indexes
   (from `services/data-archive/src/doomberg_archive/schema.sql`).
2. `TRUNCATE` each target table, then bulk-`COPY` its rows in.
3. Prints per-table counts and total.

It is **idempotent**: re-running truncates-then-loads, so the end state is identical.

Flags:
- `--json PATH` — override the archive JSON location (default `data/v1_archive.json`).
- `--no-truncate` — append instead of replacing (not recommended; breaks idempotency).
- `--no-create-schema` — skip DDL if the schema already exists.

## Expected output (per-table counts)

| table | rows | | table | rows |
|---|---|---|---|---|
| inst_holdings | 134349 | | fundamentals | 671 |
| ohlcv | 81832 | | etf_holdings | 310 |
| insider_transactions | 14376 | | sentiment | 178 |
| news | 5672 | | analyst_ratings | 155 |
| congress_trades | 1002 | | inst_filings | 32 |
| fundamentals_pit | 903 | | sectors | 27 |
| universe | 683 | | macro_prices | 16 |
| | | | macro_quotes | 14 |

Total: **240,220** rows.

## Production target — DigitalOcean Managed Postgres

> **BLOCKED on the DO credential.** No DO API token / connection string is present yet
> (`infra/terraform/.env` absent). Everything up to the credentialed step is done. The
> remaining step is purely: obtain the DO Managed Postgres DSN and run the command above.

When the Managed Postgres database is provisioned (Stream 2 / infra), get its connection
string from the DO control panel or `doctl databases connection <id> --format URI`, then:

```bash
export DOOMBERG_ARCHIVE_URL='postgresql://doadmin:<pw>@<host>:25060/defaultdb?sslmode=require'
uv run python scripts/import_v1_archive.py
```

Notes for DO Managed PG:
- The connection URI uses port `25060` and **requires** `sslmode=require` — keep it in the DSN.
- The default DB is `defaultdb`; create/point at a dedicated DB if desired.
- Loading ~240k rows via `COPY` over the network typically completes in well under a minute.

The same `DOOMBERG_ARCHIVE_URL` is what `doomberg_archive.gateway.PgArchiveGateway(dsn)`
reads at runtime, so the read seam is wired the moment the load finishes. In prod the
archive may share the same `DOOMBERG_DB` Postgres instance (different schema).

## Verifying after load

```bash
psql "$DOOMBERG_ARCHIVE_URL" -c "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname='archive' ORDER BY n_live_tup DESC;"
```

Or via the gateway:

```python
from doomberg_archive import PgArchiveGateway
gw = PgArchiveGateway("$DOOMBERG_ARCHIVE_URL")
print(gw.macro())                      # {prices: [...], quotes: [...]}
print(len(gw.universe(tracked_only=True)))
dates, closes, syms = gw.ohlcv_panel(["NVDA", "AMD"])  # (T,), (T,N), (N,)
```
