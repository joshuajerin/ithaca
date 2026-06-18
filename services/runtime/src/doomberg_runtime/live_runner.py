"""Paper-live worker: ``run_paper_tick``.

ONE stateless tick of a promoted paper deployment:

1. Load the universe's CURRENT marks via the core gateway on REAL current data,
   under an aggregate wall-clock deadline.
2. Max-staleness gate: if the freshest mark is older than ``max_staleness_s``,
   SKIP-AND-ALERT (emit a ``denial``) rather than trade on stale data.
3. Evaluate the spec to TARGET weights using the same core graph/accounting the
   backtest uses (backtest-math == paper-math).
4. Compute a book delta from the current book weights to the target weights and
   PROPOSE it. The worker is stateless and does NOT write the book — the control
   plane is the single writer of the money path and applies the delta under a lock.

Emits ``mark`` (the marks it priced on) and ``fill`` (the proposed deltas) trace
events. Returns a proposal dict ``{action, deltas, ...}`` for the control plane.
Never ``except: pass`` on the audited path — failures emit ``denial``/``error``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from doomberg_core import Core
from doomberg_core.graph import evaluate as _evaluate

from ._trace import emit
from .deadline import Deadline, DeadlineExceeded

__all__ = ["run_paper_tick", "DEFAULT_BUDGET_MS", "DEFAULT_MAX_STALENESS_S"]

DEFAULT_BUDGET_MS = 15_000
# A daily-close paper strategy tolerates a stale-ish mark; tighten per deployment.
DEFAULT_MAX_STALENESS_S = 6 * 60 * 60  # 6 hours


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        s = ts.replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def run_paper_tick(
    tenant_id: str,
    run_id: str,
    *,
    platform: Any,
    core: Core,
    book: dict[str, Any] | None = None,
    budget_ms: int = DEFAULT_BUDGET_MS,
    max_staleness_s: float = DEFAULT_MAX_STALENESS_S,
    deadline: Deadline | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run one stateless paper tick; return a book-delta PROPOSAL (never writes the book).

    ``book`` is the control-plane-owned current book snapshot
    ``{capital, weights:{sym:w}}`` (defaults to flat/all-cash). ``now`` is injectable
    for deterministic staleness tests.
    """
    tenant_id = str(tenant_id)
    run_id = str(run_id)
    runs = platform.runs
    trace = platform.trace
    dl = deadline or Deadline.from_ms(budget_ms)
    now = now or datetime.now(timezone.utc)
    book = book or {"capital": 0.0, "weights": {}}
    cur_weights: dict[str, float] = {k: float(v) for k, v in (book.get("weights") or {}).items()}

    run = runs.get(tenant_id, run_id)
    if run is None:
        emit(trace, tenant_id=tenant_id, run_id=run_id, type="error",
             data={"stage": "load", "error": "run not found"})
        raise KeyError(f"run not found: {run_id}")

    spec = run.get("spec")
    if not isinstance(spec, dict) or "universe" not in spec:
        emit(trace, tenant_id=tenant_id, run_id=run_id, type="error",
             data={"stage": "load", "error": "run has no usable spec"})
        raise ValueError(f"run {run_id} has no usable spec")

    symbols = [str(s) for s in spec["universe"]["symbols"]]

    try:
        dl.check("paper:start")

        # --- 1. current marks on REAL current data ---------------------------------
        # We pull a trailing window (not a single bar): a primitive needs its warm-up
        # history to produce a signal, and the LAST bar of that window is the current
        # mark. This is the same gateway seam the backtest uses (price_panel), so
        # paper-math == backtest-math. as_of=None => through "now" (real current data).
        panel, prov = core.gateway.price_panel(symbols, range_="1y", as_of=None)
        provenance = prov.get("provenance") or {}
        coverage_missing = list(panel.missing or [])
        priced_syms = list(panel.symbols)
        marks: dict[str, float] = {}
        freshest: datetime | None = None
        if panel.dates and priced_syms:
            last = panel.closes[-1]
            marks = {priced_syms[i].upper(): float(last[i]) for i in range(len(priced_syms))}
            freshest = _parse_iso(provenance.get("as_of")) or _parse_iso(panel.dates[-1])

        emit(trace, tenant_id=tenant_id, run_id=run_id, type="mark",
             data={"marks": marks, "missing": coverage_missing,
                   "bars": len(panel.dates), "as_of": freshest.isoformat() if freshest else None})

        # --- 2. max-staleness gate: skip-and-alert, never fill on stale data --------
        if not marks:
            emit(trace, tenant_id=tenant_id, run_id=run_id, type="denial",
                 data={"reason": "no_marks", "detail": "no priced symbols this tick",
                       "missing": coverage_missing})
            return {"action": "skip", "reason": "no_marks", "deltas": {}, "missing": coverage_missing}

        if freshest is None:
            stale_age_s = float("inf")
        else:
            stale_age_s = max(0.0, (now - freshest).total_seconds())
        if stale_age_s > max_staleness_s:
            emit(trace, tenant_id=tenant_id, run_id=run_id, type="denial",
                 data={"reason": "stale_data", "stale_age_s": stale_age_s,
                       "max_staleness_s": max_staleness_s,
                       "as_of": freshest.isoformat() if freshest else None})
            return {"action": "skip", "reason": "stale_data",
                    "stale_age_s": stale_age_s, "deltas": {}}

        # --- 3. evaluate spec -> target weights (same core graph as the backtest) ---
        dl.check("paper:evaluate")
        graph = _evaluate(spec, panel.dates, panel.closes)
        w_row = graph["weights"][-1]
        target_weights = {priced_syms[i].upper(): round(float(w_row[i]), 6)
                          for i in range(len(priced_syms)) if abs(w_row[i]) > 1e-9}

        # --- 4. compute book delta and PROPOSE (control plane applies it) -----------
        all_syms = set(cur_weights) | set(target_weights)
        deltas = {
            s: round(target_weights.get(s, 0.0) - cur_weights.get(s, 0.0), 6)
            for s in sorted(all_syms)
        }
        deltas = {s: d for s, d in deltas.items() if abs(d) > 1e-9}

        emit(trace, tenant_id=tenant_id, run_id=run_id, type="fill",
             data={"proposed": True, "deltas": deltas, "targetWeights": target_weights,
                   "currentWeights": cur_weights, "marks": marks,
                   "relaxed": graph["anyRelaxed"], "risk": graph["worstAttest"]})

        # The worker PROPOSES only — the control plane writes the book under a lock.
        return {
            "action": "propose",
            "deltas": deltas,
            "targetWeights": target_weights,
            "currentWeights": cur_weights,
            "marks": marks,
            "as_of": freshest.isoformat() if freshest else None,
            "relaxed": graph["anyRelaxed"],
            "risk": graph["worstAttest"],
        }

    except DeadlineExceeded as exc:
        emit(trace, tenant_id=tenant_id, run_id=run_id, type="denial",
             data={"reason": "deadline_exceeded", "detail": str(exc)})
        return {"action": "skip", "reason": "deadline_exceeded", "deltas": {}}
    except Exception as exc:  # noqa: BLE001 — audited: emit error, never swallow.
        emit(trace, tenant_id=tenant_id, run_id=run_id, type="error",
             data={"stage": "paper_tick", "error": type(exc).__name__, "detail": str(exc)[:500]})
        raise
