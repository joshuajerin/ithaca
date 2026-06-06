---
name: api-server Python test conventions
description: How tests are written/run for the api-server Python backend (no pytest installed; self-running standalone files).
---

The `artifacts/api-server/tests/*.py` suites are **standalone**, not pytest-driven
(pytest is NOT installed in this env). Each file ends with a `_run_all()` that
collects `test_*` globals and runs them, guarded by `if __name__ == "__main__"`.
Run one with `python artifacts/api-server/tests/test_X.py`. They also work under
pytest if it ever gets added, so keep both entry points.

**Import shim:** every test prepends the artifact dir to `sys.path`
(`_API_SERVER_DIR = .../artifacts/api-server`) so `from app import ...` resolves
regardless of cwd. The package can't be imported as `artifacts.api-server...`
(hyphen), so this shim is required.

**Mocking the data layer (no real Postgres needed):**
- `repo` does `from . import db`, so patch the **shared `db` module object**
  (`db.db_available`, `db.query`, `db.query_one`, `db.execute`, `db.execute_many`)
  and every repo accessor follows. `available=False` forces the mock-fallback
  path and the query helpers must never be called; `available=True` + fake row
  dicts drives the "live" path; make the helpers raise to test DB-error fallback.
- Source adapters: patch `module.httpx.Client` with a stub returning a fake resp
  (`.json()` for prices, `.content` bytes for news + real `feedparser.parse`),
  and `fundamentals.yf.Ticker` with a fake exposing `.info`. This tests real
  parsing against captured Yahoo/Google payloads with zero network.
- Always save/restore the patched attr in a `try/finally` (a contextmanager is
  cleanest) so one test's stub never leaks into the next.

**Why:** the "no empty panels" guarantee (live data when DB populated, curated
`data.py` mock otherwise) plus the `asOf`/`source` freshness fields were only
verified manually before; `tests/test_datalayer.py` pins live-vs-mock for every
repo accessor and the adapter parsing/unit-quirks.
