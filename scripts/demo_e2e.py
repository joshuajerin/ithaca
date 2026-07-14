#!/usr/bin/env python
"""End-to-end demo: research -> propose -> backtest -> observe, fully in-process.

Exercises the REAL components wired together over ONE shared system-of-record:
  ithaca_platform (stores) + ithaca_core (validate/backtest) + ithaca_runtime
  (the worker job) + ithaca_rest (the UI read-model).

Network-free + deterministic (synthetic price source), so it can gate in CI.
Run:  uv run python scripts/demo_e2e.py
"""
from __future__ import annotations

import datetime as dt
import sys
import tempfile
import uuid

import numpy as np

from ithaca_core import Core, DataGateway
from ithaca_platform import Platform
from ithaca_rest import shape_run
from ithaca_runtime import run_backtest_job


# ---- synthetic, deterministic, offline price source ------------------------------------

def _trading_days(n: int, start: str = "2024-01-01") -> list[str]:
    y, m, d = (int(x) for x in start.split("-"))
    day = dt.date(y, m, d)
    out: list[str] = []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def _make_fetch(dates, series):
    def _fetch(symbol, range_="1y", interval="1d"):
        su = symbol.upper()
        if su not in series:
            raise ValueError(f"no data for {su}")
        c = series[su]
        pts = [{"d": dates[i], "o": c[i], "h": c[i], "l": c[i], "c": c[i], "v": 1e6} for i in range(len(dates))]
        return {"points": pts, "quote": {"symbol": su, "price": c[-1], "asOf": dates[-1] + "T20:00:00Z"}}
    return _fetch


SPEC = {
    "spec_version": "1.0",
    "name": "demo-dual-momentum",
    "universe": {"symbols": ["AAA", "BBB", "CCC"], "source": "prices"},
    "strategy": {"id": "rank_returns", "params": {"lookback": 60, "top": 2}},
    "construction": {"scheme": "rank_weight", "long_only": True, "gross": 1.0},
    "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.6},
    "execution": {"cost_bps": 5, "algo": "vwap", "rebalance": "monthly@close"},
    "seed": 42,
}


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")
    raise SystemExit(1)


def main() -> int:
    dates = _trading_days(250)
    rng = np.random.default_rng(11)
    series = {s: list(100 * np.cumprod(1 + rng.normal(dr, 0.012, 250)))
              for s, dr in {"AAA": 0.0011, "BBB": 0.0003, "CCC": -0.0006}.items()}

    tenant = str(uuid.uuid4())
    other_tenant = str(uuid.uuid4())
    db_path = tempfile.mktemp(suffix=".db")
    platform = Platform(db_path)                       # one shared system-of-record (real SQLite)
    core = Core(DataGateway(fetch_history=_make_fetch(dates, series)))  # offline core

    print("Ithaca v2 — end-to-end demo (research → propose → backtest → observe)\n")

    # 1) PROPOSE (control-plane logic): validate the declarative spec, persist a draft.
    validated = core.validate_spec(SPEC)               # raises on any closed-schema violation
    sv = platform.strategies.create(tenant, validated)
    print(f"  ✓ proposed strategy {sv['id']} v{sv['version']} ({SPEC['name']})")

    # closed-schema invariant: a smuggled code field must be rejected
    try:
        core.validate_spec({**SPEC, "code": "import os"})
        _fail("free-form code field was NOT rejected")
    except Exception:
        print("  ✓ free-form code field rejected (no agent code is ever run)")

    # 2) CREATE a backtest run (queued), as the control plane would.
    run_id = platform.runs.create(tenant, "backtest", sv["id"], validated)
    platform.runs.transition(tenant, run_id, "queued", expect=0)
    print(f"  ✓ created backtest run {run_id[:8]}… (queued)")

    # 3) RUNTIME executes the job (queued → running → succeeded), streaming trace events.
    run = run_backtest_job(tenant, run_id, platform=platform, core=core)
    if run["state"] != "succeeded":
        _fail(f"run ended in state {run['state']!r}, expected succeeded")
    result = run["result"]["data"]
    stats = result["stats"]
    print(f"  ✓ backtest succeeded: {result['bars']} bars, "
          f"sharpe={stats['sharpe']}, totalReturn={stats['totalReturn']}%, maxDD={stats['maxDD']}%")

    # risk gate must have passed (gross feasible) — the v1 311%-gross bug can't recur
    if not result["risk"]["ok"] or result["risk"]["gross"] > 1.0 + 1e-6:
        _fail(f"risk gate not satisfied: {result['risk']}")
    print(f"  ✓ risk gate satisfied: gross={result['risk']['gross']:.4f} (ok={result['risk']['ok']})")

    # 4) OBSERVE via the rest-gateway read-model + raw trace.
    events = platform.trace.events(tenant, run_id)
    seqs = [e["seq"] for e in events]
    if seqs != list(range(len(seqs))):
        _fail(f"trace seq not gap-free: {seqs}")
    shaped = shape_run(run, events)
    timeline = shaped["trace"]["timeline"]
    print(f"  ✓ trace is gap-free: {len(events)} events, seq 0..{seqs[-1]} "
          f"(types: {sorted({e['type'] for e in events})})")
    print(f"  ✓ read-model shaped {len(timeline)} timeline item(s) for the UI")

    # 5) TENANT ISOLATION: another tenant cannot see this run.
    if platform.runs.get(other_tenant, run_id) is not None:
        _fail("tenant isolation breached — another tenant read the run")
    if platform.trace.events(other_tenant, run_id):
        _fail("tenant isolation breached — another tenant read the trace")
    print("  ✓ tenant isolation holds (cross-tenant reads return nothing)")

    print("\nPASS — full pipeline works end-to-end on one shared system-of-record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
