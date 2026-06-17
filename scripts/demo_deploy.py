#!/usr/bin/env python
"""Deploy-layer demo: the conductor drives the loops end-to-end, no manual job calls.

Proves the two pieces the earlier slice left unwired:
  1. BACKTEST ORCHESTRATION — a run created via the control-plane actions lands ``queued``;
     the runtime ``BacktestWorker`` *pulls the queue* and executes it to ``succeeded`` with no
     hand-rolled ``run_backtest_job`` call.
  2. PAPER MONEY PATH — a paper run is promoted + activated to ``live``; the ``PaperScheduler``
     ticks it, the runtime proposes a book delta, and the control-plane single-writer
     ``apply_paper_delta`` re-gates and writes the book (emitting an applied ``fill``).

Network-free + deterministic (synthetic, recent-dated price source). Run:
    uv run python scripts/demo_deploy.py
"""
from __future__ import annotations

import datetime as dt
import sys
import tempfile
import uuid

import numpy as np

from doomberg_control import actions
from doomberg_control.deps import Ctx
from doomberg_control.money import make_applier
from doomberg_core import Core, DataGateway
from doomberg_platform import Platform
from doomberg_runtime import AlwaysOpen, BacktestWorker, PaperScheduler


def _recent_trading_days(n: int) -> list[str]:
    """n trading days ending today (UTC) so the paper staleness gate passes on real wall clock."""
    out: list[str] = []
    day = dt.datetime.now(dt.timezone.utc).date()
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= dt.timedelta(days=1)
    return sorted(out)


def _make_fetch(dates, series):
    def _fetch(symbol, range_="1y", interval="1d"):
        su = symbol.upper()
        if su not in series:
            raise ValueError(f"no data for {su}")
        c = series[su]
        pts = [{"d": dates[i], "o": c[i], "h": c[i], "l": c[i], "c": c[i], "v": 1e6}
               for i in range(len(dates))]
        return {"points": pts, "quote": {"symbol": su, "price": c[-1], "asOf": dates[-1] + "T20:00:00Z"}}
    return _fetch


SPEC = {
    "spec_version": "1.0",
    "name": "deploy-demo-dual-momentum",
    "universe": {"symbols": ["AAA", "BBB", "CCC"], "source": "prices"},
    "strategy": {"id": "rank_returns", "params": {"lookback": 60, "top": 2}},
    "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
    "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.6},
    "execution": {"cost_bps": 5, "algo": "vwap", "rebalance": "daily@close"},
    "seed": 42,
}


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")
    raise SystemExit(1)


def main() -> int:
    dates = _recent_trading_days(250)
    rng = np.random.default_rng(11)
    series = {s: list(100 * np.cumprod(1 + rng.normal(dr, 0.012, 250)))
              for s, dr in {"AAA": 0.0011, "BBB": 0.0003, "CCC": -0.0006}.items()}

    tenant = str(uuid.uuid4())
    other = str(uuid.uuid4())
    platform = Platform(tempfile.mktemp(suffix=".db"))
    core = Core(DataGateway(fetch_history=_make_fetch(dates, series)))
    human = Ctx(tenant_id=tenant, actor_kind="user", actor_id="trader-1")

    print("Doomberg v2 — deploy-layer demo (conductor drives the loops)\n")

    # === 1) BACKTEST ORCHESTRATION =====================================================
    sid = actions.propose_strategy(platform, human, core, SPEC)["id"]
    bt = actions.create_run(platform, human, strategy_id=sid, kind="backtest")
    print(f"  ✓ control plane enqueued backtest {bt['run_id'][:8]}… ({bt['state']})")

    worker = BacktestWorker(platform, core)
    summary = worker.poll_once()                      # <-- pulls the queue itself
    if summary["succeeded"] != [bt["run_id"]]:
        _fail(f"worker did not drain the queued backtest: {summary}")
    run = platform.runs.get(tenant, bt["run_id"])
    stats = run["result"]["data"]["stats"]
    print(f"  ✓ worker pulled + ran it to {run['state']} "
          f"(sharpe={stats['sharpe']}, no manual job call)")

    # === 2) PAPER MONEY PATH ============================================================
    paper = actions.create_run(platform, human, strategy_id=sid, kind="paper")
    pid = paper["run_id"]
    actions.promote_run(platform, human, pid)         # human + gate
    state = actions.activate_run(platform, human, pid)["state"]   # promoted -> live
    print(f"  ✓ paper run {pid[:8]}… promoted + activated ({state})")

    scheduler = PaperScheduler(platform, core, make_applier(platform), calendar=AlwaysOpen())
    results = scheduler.tick_once()                   # <-- ticks every live deployment
    if not results or results[0].get("applied", {}).get("applied") is not True:
        _fail(f"scheduler did not apply a paper delta: {results}")
    book = platform.books.get(tenant, pid)
    if not book or not book["weights"]:
        _fail("paper book was not written by the single-writer apply")
    print(f"  ✓ scheduler ticked; control plane applied the delta -> book {book['weights']} "
          f"(gross={book['gross']}, v{book['version']})")

    fills = [e for e in platform.trace.events(tenant, pid) if e["type"] == "fill"]
    if not fills or fills[-1]["data"]["applied"] is not True:
        _fail("no applied fill was traced on the money path")
    print(f"  ✓ applied fill traced (deltas={fills[-1]['data']['deltas']})")

    # === 3) TENANT ISOLATION ============================================================
    if platform.runs.get(other, pid) is not None or platform.books.get(other, pid) is not None:
        _fail("tenant isolation breached on the deploy layer")
    print("  ✓ tenant isolation holds across runs + books")

    print("\nPASS — the deploy layer runs itself end-to-end (queue pulled, money path applied).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
