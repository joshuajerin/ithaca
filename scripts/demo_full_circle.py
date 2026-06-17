#!/usr/bin/env python
"""Full-circle demo: the WHOLE platform loop through the AUTHED front door.

Where ``demo_deploy.py`` proves the conductor drives the loops, this proves the *platform*:
a tenant is onboarded, an API key is minted + verified, and every step below runs as that
authenticated principal — resolved through the SAME ``resolve_ctx`` the HTTP front doors use,
so the scopes on the key are really enforced.

The loop, end to end:
  1. ONBOARD       create a tenant, mint a scoped API key, verify it.
  2. AUTHED CTX    resolve the key -> a BYO-agent ctx (carries exactly its scopes).
  3. PROPOSE       the agent authors a strategy (needs ``strategy:author``).
  4. BACKTEST      the agent requests a backtest (needs ``deploy:backtest``); the conductor
                   (BacktestWorker) pulls the queue and runs it to ``succeeded``.
  5. PAPER REQUEST the agent requests a paper run (needs ``deploy:paper``)...
  6. PROMOTE       ...but CANNOT self-promote (agent actor blocked); a HUMAN promotes +
                   activates the deployment to ``live``.
  7. TICK          the PaperScheduler ticks the live deployment; the control-plane single
                   writer applies the book delta and traces an applied ``fill``.
  8. OBSERVE       the trace is gap-free (seq 0..N) and the book holds positions.
  9. ISOLATE       a second tenant sees none of it; its key cannot touch tenant A's runs.

Network-free + deterministic (synthetic, recent-dated prices). Run:
    uv run python scripts/demo_full_circle.py
"""
from __future__ import annotations

import datetime as dt
import sys
import tempfile

import numpy as np

from doomberg_control import actions
from doomberg_control.actions import ActionError
from doomberg_control.deps import Ctx, resolve_ctx
from doomberg_control.money import make_applier
from doomberg_core import Core, DataGateway
from doomberg_platform import Platform
from doomberg_runtime import AlwaysOpen, BacktestWorker, PaperScheduler


def _recent_trading_days(n: int) -> list[str]:
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
        return {"points": pts,
                "quote": {"symbol": su, "price": c[-1], "asOf": dates[-1] + "T20:00:00Z"}}
    return _fetch


SPEC = {
    "spec_version": "1.0",
    "name": "full-circle-dual-momentum",
    "universe": {"symbols": ["AAA", "BBB", "CCC"], "source": "prices"},
    "strategy": {"id": "rank_returns", "params": {"lookback": 60, "top": 2}},
    "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
    "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.6},
    "execution": {"cost_bps": 5, "algo": "vwap", "rebalance": "daily@close"},
    "seed": 42,
}

# The launch scope set a BYO agent gets: author + request, never self-promote.
AGENT_SCOPES = ["data:read", "strategy:author", "deploy:backtest", "deploy:paper"]


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")
    raise SystemExit(1)


def _agent_ctx(platform: Platform, key: str) -> Ctx:
    """Turn a presented bearer key into a ctx via the SAME resolver the HTTP doors use."""
    return resolve_ctx(
        platform,
        authorization=f"Bearer {key}",
        x_tenant_id=None,
        x_actor_kind=None,   # an API key is an agent principal by default
        x_actor_id=None,
    )


def main() -> int:
    dates = _recent_trading_days(250)
    rng = np.random.default_rng(11)
    series = {s: list(100 * np.cumprod(1 + rng.normal(dr, 0.012, 250)))
              for s, dr in {"AAA": 0.0011, "BBB": 0.0003, "CCC": -0.0006}.items()}

    platform = Platform(tempfile.mktemp(suffix=".db"))
    core = Core(DataGateway(fetch_history=_make_fetch(dates, series)))

    print("Doomberg v2 — full-circle demo (authed front door, whole loop)\n")

    # === 1) ONBOARD: tenant + API key ===================================================
    tenant = platform.auth.create_tenant("Acme Capital")
    key, key_id = platform.auth.mint_key(tenant, AGENT_SCOPES)
    parts = key.split("_", 3)
    if not (parts[0] == "dmbg" and len(parts) == 4 and parts[2] == key_id):
        _fail(f"minted key not in dmbg_<env>_<keyid>_<secret> format: {key!r}")
    print(f"  ✓ onboarded tenant {tenant[:8]}… + minted key dmbg_…_{key_id[:8]}… "
          f"(scopes={AGENT_SCOPES})")

    # === 2) AUTHED CTX: verify the key, resolve a principal =============================
    principal = platform.auth.verify(key)
    if principal is None or principal["tenant_id"] != tenant:
        _fail("key did not verify back to its tenant")
    agent = _agent_ctx(platform, key)
    if agent.tenant_id != tenant or agent.actor_kind != "agent":
        _fail("resolved ctx is not the expected agent principal")
    if set(agent.scopes) != set(AGENT_SCOPES):
        _fail(f"resolved ctx scopes wrong: {sorted(agent.scopes)}")
    print(f"  ✓ key verified + resolved to agent ctx (tenant-bound, scope-bound)")

    # A scope-too-low key is genuinely refused (prove enforcement, not just defaults).
    weak_key, _ = platform.auth.mint_key(tenant, ["data:read"])
    weak = _agent_ctx(platform, weak_key)
    try:
        actions.propose_strategy(platform, weak, core, SPEC)
        _fail("a data:read-only key was allowed to author a strategy")
    except ActionError as exc:
        if exc.status != 403:
            _fail(f"scope-too-low should be 403, got {exc.status}")
    print("  ✓ scope enforced: a data:read-only key is refused authoring (403)")

    # === 3) PROPOSE (as the agent, needs strategy:author) ===============================
    sid = actions.propose_strategy(platform, agent, core, SPEC)["id"]
    print(f"  ✓ agent proposed strategy {sid[:8]}…")

    # === 4) BACKTEST: agent requests, conductor pulls + runs ============================
    bt = actions.create_run(platform, agent, strategy_id=sid, kind="backtest")
    worker = BacktestWorker(platform, core)
    summary = worker.poll_once()
    if summary["succeeded"] != [bt["run_id"]]:
        _fail(f"worker did not drain the queued backtest: {summary}")
    run = platform.runs.get(tenant, bt["run_id"])
    stats = run["result"]["data"]["stats"]
    print(f"  ✓ agent requested backtest; conductor ran it to {run['state']} "
          f"(sharpe={stats['sharpe']})")

    # === 5) PAPER REQUEST (agent) =======================================================
    paper = actions.create_run(platform, agent, strategy_id=sid, kind="paper")
    pid = paper["run_id"]
    print(f"  ✓ agent requested paper deployment {pid[:8]}… ({paper['state']})")

    # === 6) PROMOTE: agent CANNOT, a human CAN =========================================
    try:
        actions.promote_run(platform, agent, pid)
        _fail("agent was allowed to self-promote (the human-actor rule failed)")
    except ActionError as exc:
        if exc.status != 403:
            _fail(f"agent promote should be 403, got {exc.status}")
    print("  ✓ agent self-promotion refused (403) — needs a human")

    human = Ctx(tenant_id=tenant, actor_kind="user", actor_id="trader-1")
    actions.promote_run(platform, human, pid)
    state = actions.activate_run(platform, human, pid)["state"]
    if state != "live":
        _fail(f"human promote+activate did not reach live: {state}")
    print(f"  ✓ human promoted + activated the deployment ({state})")

    # === 7) TICK: scheduler ticks; single writer applies the delta ======================
    scheduler = PaperScheduler(platform, core, make_applier(platform), calendar=AlwaysOpen())
    results = scheduler.tick_once()
    if not results or results[0].get("applied", {}).get("applied") is not True:
        _fail(f"scheduler did not apply a paper delta: {results}")
    book = platform.books.get(tenant, pid)
    if not book or not book["weights"]:
        _fail("paper book was not written by the single-writer apply")
    print(f"  ✓ scheduler ticked; control plane applied -> book {book['weights']} "
          f"(gross={book['gross']}, v{book['version']})")

    # === 8) OBSERVE: gap-free trace + applied fill ======================================
    events = platform.trace.events(tenant, pid)
    seqs = [e["seq"] for e in events]
    if seqs != list(range(len(seqs))):
        _fail(f"trace seq is not gap-free: {seqs}")
    fills = [e for e in events if e["type"] == "fill"]
    if not fills or fills[-1]["data"]["applied"] is not True:
        _fail("no applied fill was traced on the money path")
    print(f"  ✓ trace is gap-free (seq 0..{seqs[-1]}); applied fill recorded "
          f"(deltas={fills[-1]['data']['deltas']})")

    # === 9) ISOLATE: a second tenant sees nothing of tenant A ===========================
    other = platform.auth.create_tenant("Rival LLC")
    other_key, _ = platform.auth.mint_key(other, AGENT_SCOPES)
    other_ctx = _agent_ctx(platform, other_key)
    if other_ctx.tenant_id == tenant:
        _fail("two tenants resolved to the same id")
    if platform.runs.get(other, pid) is not None or platform.books.get(other, pid) is not None:
        _fail("tenant isolation breached: tenant B can read tenant A's run/book")
    if platform.strategies.get(other, sid) is not None:
        _fail("tenant isolation breached: tenant B can read tenant A's strategy")
    # Tenant B's key cannot create a run against tenant A's strategy (not found for B).
    try:
        actions.create_run(platform, other_ctx, strategy_id=sid, kind="backtest")
        _fail("tenant B created a run against tenant A's strategy")
    except ActionError as exc:
        if exc.status != 404:
            _fail(f"cross-tenant strategy ref should be 404, got {exc.status}")
    print("  ✓ tenant isolation holds across keys, runs, books, and strategies")

    print("\nPASS — full circle: onboard -> authed propose -> backtest -> human promote -> "
          "paper tick -> gap-free trace + book, with tenant isolation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
