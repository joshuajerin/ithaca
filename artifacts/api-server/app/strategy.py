"""Strategy lifecycle service: research → backtest → paper → live → retired.

This is the orchestration layer that ties the existing pillars together — it does
NOT re-implement them. Target weights come from the signal library (rank the
universe by a real signal) or from explicit names; a paper book is built from
those weights via the Execution pillar's ``generate_orders`` and then marked to
market against REAL prices by ``engine.paperbook``. Stage transitions and the
user-set promotion criteria are persisted via ``strategy_store``.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import compliance_store, engine, repo, strategy_store

# Stages whose books are actively marked end-of-day and accrue a track record.
ACTIVE_STAGES = ("paper", "live")

log = logging.getLogger(__name__)


class ComplianceBlock(Exception):
    """Raised when a pre-trade gate refuses to apply a trade list / book.

    Carries the full gate ``result`` so callers (HTTP routes, the agent) can
    surface the specific violations and render the compliance panel instead of
    a generic error.
    """

    def __init__(self, result: dict, action: str = "trade", view: Optional[dict] = None):
        self.result = result or {}
        self.action = action
        self.view = view
        reason = self.result.get("reason") or "Trade blocked by compliance"
        super().__init__(reason)


def _gate_weights(positions: List[dict], prices: Dict[str, float], nav: float) -> Dict[str, float]:
    """Signed NAV-fraction weights for a resulting book, used by the gate."""
    out: Dict[str, float] = {}
    if nav <= 0:
        return out
    for p in positions or []:
        s = (p.get("symbol") or "").upper()
        if not s:
            continue
        px = prices.get(s) or float(p.get("entryPrice") or 0.0)
        out[s] = (float(p.get("shares") or 0.0) * px) / nav
    return out


def prospective_weights(view: dict) -> Dict[str, float]:
    """The resulting-book weights a trade would produce for ``view``.

    Uses the live marked book when one exists (paper/live), otherwise the target
    weights — i.e. what ``paper_trade`` would open. Drives the read-only
    "is this trade allowed?" check.
    """
    positions = view.get("positions") or []
    if positions:
        syms = [(p.get("symbol") or "").upper() for p in positions]
        prices = _price_map(syms)
        cash = float(view.get("cash") or 0.0)
        book_val = engine.paperbook.book_value(positions, cash, prices)
        return _gate_weights(positions, prices, book_val)
    wmap = view.get("targetWeights") or {}
    if not wmap:
        wmap, _picks, _excl, _label = derive_target_weights(view.get("signal"), None, None, None)
    return {(s or "").upper(): float(w) for s, w in wmap.items()}


def check_strategy(view: dict) -> dict:
    """Read-only pre-trade gate for a strategy's prospective book (no audit)."""
    return precheck(view, prospective_weights(view), "check",
                    raise_on_block=False, audit=False)


def precheck(view: dict, weights: Dict[str, float], action: str,
             raise_on_block: bool = True, audit: bool = True) -> dict:
    """Run the pre-trade gate over a resulting book, write an audit entry, and
    (by default) raise ``ComplianceBlock`` on a hard violation.

    The gate considers the persisted firm limits, restricted + watch lists and
    both the global and per-strategy kill switches. Every call is audited —
    allowed, warned or blocked — so there is a complete trail of decisions.
    """
    cfg = compliance_store.get_config()
    sid = view.get("id")
    killed, kreason = compliance_store.is_killed(sid)
    result = engine.compliance.evaluate_gate(
        weights=weights,
        limits=cfg.get("limits"),
        restricted=cfg.get("restricted"),
        watch=cfg.get("watch"),
        kill_switch=killed,
        kill_reason=kreason,
    )
    if result["blocked"]:
        decision = "blocked"
        summary = result.get("reason") or "Trade blocked by compliance"
    elif result["warnings"]:
        decision = "warn"
        summary = "; ".join(result["warnings"])
    else:
        decision = "allowed"
        summary = "All pre-trade checks passed"
    if audit:
        compliance_store.append_audit(
            action=action,
            decision=decision,
            summary=summary,
            strategy_id=sid,
            strategy_name=view.get("name"),
            detail={
                "checks": result["checks"],
                "metrics": result["metrics"],
                "restricted": result["restricted"],
                "watch": result["watch"],
                "violations": result["violations"],
                "warnings": result["warnings"],
            },
        )
    if result["blocked"] and raise_on_block:
        raise ComplianceBlock(result, action=action, view=view)
    return result


DEFAULT_CAPITAL = 1_000_000.0
DEFAULT_TOP_N = 8
_UNIVERSE_CAP = 40
# Modeled one-side transaction cost applied to traded notional on a rebalance.
DEFAULT_COST_BPS = 5.0

# Ordered promotion ladder; retired is terminal and reachable from anywhere.
STAGE_ORDER = ["research", "backtest", "paper", "live"]
ALL_STAGES = STAGE_ORDER + ["retired"]

# Defaults applied when the user does not set their own promotion bar. These are
# the gates a paper book must clear (on REAL realized stats) to go live.
DEFAULT_CRITERIA = {
    "minSharpe": 0.5,
    "minReturnPct": 0.0,
    "maxDrawdownPct": 25.0,
    "minDays": 5,
}


# --------------------------- helpers ---------------------------
def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "strategy").lower()).strip("-")
    return s or "strategy"


def _new_id(name: str) -> str:
    return f"{_slug(name)[:24]}-{uuid.uuid4().hex[:6]}"


def _resolve_universe(symbols: List[str], sector: Optional[str]) -> Tuple[List[str], str]:
    if symbols:
        return symbols[:_UNIVERSE_CAP], f"{len(symbols)} selected names"
    sid = repo.resolve_sector(sector) if sector else None
    if sid:
        syms = repo.symbols_in_sector(sid)
        if len(syms) >= 5:
            return syms[:_UNIVERSE_CAP], repo.sector_name(sid)
    return repo.all_symbols()[:_UNIVERSE_CAP], "US large-cap universe"


def derive_target_weights(
    signal: Optional[str],
    symbols: Optional[List[str]],
    weights: Optional[List[float]],
    sector: Optional[str],
    top_n: int = DEFAULT_TOP_N,
) -> Tuple[Dict[str, float], List[dict], List[str], str]:
    """Return (weights, picks, excluded, universe_label).

    Explicit ``symbols`` (optionally with matching ``weights``) win; otherwise the
    universe is ranked by the real signal value at the latest date and the top
    ``top_n`` names are equal-weighted long. Names lacking data are excluded and
    reported, never imputed.
    """
    syms = [s.upper() for s in (symbols or []) if repo.get_company(s.upper())]
    if syms and weights and len(weights) == len(syms):
        tot = sum(abs(w) for w in weights) or 1.0
        wmap = {s: round(w / tot, 6) for s, w in zip(syms, weights)}
        picks = [{"symbol": s, "weight": round(wmap[s] * 100.0, 2), "score": None} for s in syms]
        return wmap, picks, [], f"{len(syms)} specified names"

    sig = engine.normalize_signal(signal or "momentum")
    meta = engine.SIGNAL_META.get(sig, {})
    universe, label = _resolve_universe(syms, sector)
    bulk = repo.price_closes_bulk(universe, days=220)
    series = bulk.get("series", {})

    scored: List[Tuple[str, float]] = []
    excluded: List[str] = []
    for s in universe:
        pts = series.get(s) or []
        closes = np.array([p["c"] for p in pts if p.get("c") is not None], dtype=float)
        ctx: dict = {}
        if meta.get("kind") == "fundamental":
            c = repo.get_company(s) or {}
            fval = None
            if sig == "value":
                pe = c.get("peRatio")
                if pe is not None and pe > 0:
                    fval = 1.0 / float(pe)
            elif sig == "quality":
                nm = c.get("netMargin")
                if nm not in (None, 0.0):
                    fval = float(nm)
            if fval is None:
                excluded.append(s)
                continue
            ctx["fval"] = fval
            closes = closes if closes.size >= 1 else np.array([1.0])
        elif closes.size < 2:
            excluded.append(s)
            continue
        arr = engine.SIGNALS[sig](closes, ctx)
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            excluded.append(s)
            continue
        scored.append((s, float(finite[-1])))

    scored.sort(key=lambda t: t[1], reverse=True)
    top = scored[: max(1, top_n)]
    if not top:
        return {}, [], excluded, label
    w = round(1.0 / len(top), 6)
    wmap = {s: w for s, _ in top}
    picks = [{"symbol": s, "weight": round(w * 100.0, 2), "score": round(sc, 4)} for s, sc in top]
    return wmap, picks, excluded, label


def _price_map(symbols: List[str]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for s in symbols:
        c = repo.get_company(s)
        if c and c.get("price"):
            out[s.upper()] = float(c["price"])
    return out


def _persist(view: dict) -> dict:
    """Map the camelCase view back to the store's column record and upsert."""
    record = {
        "id": view["id"],
        "name": view.get("name"),
        "signal": view.get("signal"),
        "construction": view.get("construction"),
        "stage": view.get("stage"),
        "capital": view.get("capital"),
        "cash": view.get("cash"),
        "inception_date": view.get("inceptionDate"),
        "positions": view.get("positions"),
        "target_weights": view.get("targetWeights"),
        "promotion_criteria": view.get("promotionCriteria"),
        "stage_history": view.get("stageHistory"),
        "notes": view.get("notes"),
    }
    if view.get("createdAt"):
        record["created_at"] = view["createdAt"]
    return strategy_store.upsert(record)


# --------------------------- lifecycle ---------------------------
def create_strategy(
    name: Optional[str] = None,
    signal: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    weights: Optional[List[float]] = None,
    sector: Optional[str] = None,
    construction: Optional[dict] = None,
    capital: Optional[float] = None,
    promotion_criteria: Optional[dict] = None,
    notes: Optional[str] = None,
    paper: bool = False,
) -> dict:
    sig = engine.normalize_signal(signal or "momentum")
    if not name:
        name = f"{engine.signal_label(sig)} Strategy"
    wmap, picks, excluded, label = derive_target_weights(sig, symbols, weights, sector)

    cons = dict(construction or {})
    cons.setdefault("universe", label)
    cons.setdefault("picks", picks)
    if excluded:
        cons["excluded"] = excluded

    crit = dict(DEFAULT_CRITERIA)
    if promotion_criteria:
        crit.update({k: v for k, v in promotion_criteria.items() if v is not None})

    sid = _new_id(name)
    view = {
        "id": sid,
        "name": name,
        "signal": sig,
        "construction": cons,
        "stage": "research",
        "capital": float(capital or DEFAULT_CAPITAL),
        "cash": None,
        "inceptionDate": None,
        "positions": None,
        "targetWeights": wmap,
        "promotionCriteria": crit,
        "stageHistory": [{"stage": "research", "at": date.today().isoformat()}],
        "notes": notes,
    }
    saved = _persist(view)
    if paper:
        saved = paper_trade(saved)
    return saved


def paper_trade(view: dict) -> dict:
    """Build a fixed-share paper book from the target weights at real prices."""
    wmap = view.get("targetWeights") or {}
    if not wmap:
        wmap, picks, excluded, label = derive_target_weights(view.get("signal"), None, None, None)
        view["targetWeights"] = wmap
    syms = list(wmap.keys())
    prices = _price_map(syms)
    capital = float(view.get("capital") or DEFAULT_CAPITAL)
    orders = engine.generate_orders(wmap, {}, prices, capital)

    positions: List[dict] = []
    invested = 0.0
    for o in orders:
        positions.append({
            "symbol": o["symbol"],
            "shares": round(o["shares"], 4),
            "entryPrice": round(o["price"], 4),
        })
        invested += o["shares"] * o["price"]
    cash = round(capital - invested, 2)

    # Pre-trade gate: validate the resulting book before it is applied.
    precheck(view, _gate_weights(positions, prices, capital), "paper_trade")

    view["positions"] = positions
    view["cash"] = cash
    view["inceptionDate"] = date.today().isoformat()
    history = list(view.get("stageHistory") or [])
    if not history or history[-1].get("stage") != "paper":
        history.append({"stage": "paper", "at": date.today().isoformat()})
    view["stageHistory"] = history
    view["stage"] = "paper"
    return _persist(view)


def _current_weights(positions: List[dict], prices: Dict[str, float], book_val: float) -> Dict[str, float]:
    """Current per-name weight fractions from marked positions over book value."""
    out: Dict[str, float] = {}
    if book_val <= 0:
        return out
    for p in positions:
        s = (p.get("symbol") or "").upper()
        px = prices.get(s)
        if px and px > 0:
            out[s] = (float(p.get("shares") or 0.0) * px) / book_val
    return out


def rebalance(view: dict, cost_bps: float = DEFAULT_COST_BPS) -> Tuple[dict, dict]:
    """Re-derive target weights, diff against the current book and apply the trades.

    Returns ``(view, info)`` where ``info`` carries the realized turnover, the
    modeled transaction cost and the trade list. The book's value continuity is
    preserved (the trades are notional-neutral apart from the modeled cost); the
    P&L baseline is re-anchored to the rebalance date because the marked-book and
    NAV model assume a single set of positions held since inception.
    """
    sig = engine.normalize_signal(view.get("signal") or "momentum")
    new_w, picks, excluded, label = derive_target_weights(sig, None, None, None)
    if not new_w:
        return view, {"applied": False, "reason": "could not derive new target weights from the signal"}

    positions = view.get("positions") or []
    # No existing book — a rebalance just establishes one from the fresh targets.
    if not positions:
        view["targetWeights"] = new_w
        cons = dict(view.get("construction") or {})
        cons["picks"] = picks
        if excluded:
            cons["excluded"] = excluded
        view["construction"] = cons
        try:
            saved = paper_trade(view)
        except ComplianceBlock as cb:
            return view, {
                "applied": False,
                "blocked": True,
                "reason": cb.result.get("reason"),
                "compliance": cb.result,
                "at": date.today().isoformat(),
            }
        capital = float(saved.get("capital") or DEFAULT_CAPITAL)
        invested = capital - float(saved.get("cash") or 0.0)
        cost = round(invested * (cost_bps / 10_000.0), 2)
        info = {
            "applied": True,
            "established": True,
            "trades": len(saved.get("positions") or []),
            "turnoverPct": 100.0,
            "costUsd": cost,
            "costBps": cost_bps,
            "at": date.today().isoformat(),
        }
        return _record_rebalance(saved, info), info

    cash = float(view.get("cash") or 0.0)
    cur_syms = [(p.get("symbol") or "").upper() for p in positions]
    all_syms = list({*cur_syms, *new_w.keys()})
    prices = _price_map(all_syms)
    book_val = engine.paperbook.book_value(positions, cash, prices)
    cur_w = _current_weights(positions, prices, book_val)

    orders = engine.generate_orders(new_w, cur_w, prices, book_val)

    pos_by_sym: Dict[str, dict] = {(p.get("symbol") or "").upper(): dict(p) for p in positions}
    traded_notional = 0.0
    cash_delta = 0.0
    for o in orders:
        s = o["symbol"]
        signed = o["shares"] if o["side"] == "buy" else -o["shares"]
        traded_notional += o["notional"]
        cash_delta += -o["notional"] if o["side"] == "buy" else o["notional"]
        existing = pos_by_sym.get(s)
        new_shares = (float(existing["shares"]) if existing else 0.0) + signed
        if new_shares <= 1e-6:
            pos_by_sym.pop(s, None)
        else:
            pos_by_sym[s] = {"symbol": s, "shares": new_shares, "entryPrice": o["price"]}

    cost = round(traded_notional * (cost_bps / 10_000.0), 2)
    new_cash = round(cash + cash_delta - cost, 2)

    # Re-anchor entry prices to the current mark so the marked-book / NAV model
    # stays internally consistent from the rebalance date forward.
    new_positions: List[dict] = []
    for s, p in pos_by_sym.items():
        px = prices.get(s) or float(p.get("entryPrice") or 0.0)
        new_positions.append({"symbol": s, "shares": round(float(p["shares"]), 4), "entryPrice": round(px, 4)})

    # Pre-trade gate: validate the resulting book before any of it is applied.
    # On a hard violation the existing book is left untouched and the caller is
    # told the rebalance was refused (no exception — the desk stays as-is).
    gate = precheck(view, _gate_weights(new_positions, prices, book_val),
                    "rebalance", raise_on_block=False)
    if gate["blocked"]:
        return view, {
            "applied": False,
            "blocked": True,
            "reason": gate.get("reason"),
            "compliance": gate,
            "at": date.today().isoformat(),
        }

    # One-way turnover = 0.5 * sum(|target - current|); equals half the gross
    # traded notional over book value.
    turnover_pct = round((traded_notional / book_val) * 50.0, 2) if book_val > 0 else 0.0

    cons = dict(view.get("construction") or {})
    cons["picks"] = picks
    if excluded:
        cons["excluded"] = excluded
    view["construction"] = cons
    view["targetWeights"] = new_w
    view["positions"] = new_positions
    view["cash"] = new_cash
    view["inceptionDate"] = date.today().isoformat()

    info = {
        "applied": True,
        "established": False,
        "trades": len(orders),
        "turnoverPct": turnover_pct,
        "costUsd": cost,
        "costBps": cost_bps,
        "tradedNotional": round(traded_notional, 2),
        "orders": [
            {"symbol": o["symbol"], "side": o["side"], "deltaWeight": o["deltaWeight"],
             "notional": round(o["notional"], 2)}
            for o in orders
        ],
        "at": date.today().isoformat(),
    }
    return _record_rebalance(view, info), info


def _record_rebalance(view: dict, info: dict) -> dict:
    """Stash the rebalance summary on construction and log a stage-history event."""
    cons = dict(view.get("construction") or {})
    cons["lastRebalance"] = {
        "at": info.get("at"),
        "trades": info.get("trades"),
        "turnoverPct": info.get("turnoverPct"),
        "costUsd": info.get("costUsd"),
        "costBps": info.get("costBps"),
    }
    view["construction"] = cons
    history = list(view.get("stageHistory") or [])
    history.append({
        "stage": view.get("stage") or "paper",
        "at": info.get("at"),
        "event": "rebalance",
        "turnoverPct": info.get("turnoverPct"),
        "costUsd": info.get("costUsd"),
        "trades": info.get("trades"),
    })
    view["stageHistory"] = history
    return _persist(view)


def mark(view: dict) -> dict:
    """Mark the book to market and resolve its real P&L history.

    Current value (marks, book value, exposures) is always computed from live
    prices. The NAV/P&L *history* now prefers the audited daily snapshot series
    persisted by the background worker; only when no snapshots exist yet (a fresh
    book or a fresh database) does it fall back to reconstructing the curve from
    real daily closes since inception. ``trackDays`` is the audited point count
    used by promotion — calendar ``ageDays`` is kept for display.
    """
    positions = view.get("positions") or []
    cash = float(view.get("cash") or 0.0)
    capital = float(view.get("capital") or DEFAULT_CAPITAL)
    inception = view.get("inceptionDate")

    syms = [p["symbol"] for p in positions]
    price_map = _price_map(syms)
    marks = engine.paperbook.position_marks(positions, price_map)
    book_val = engine.paperbook.book_value(positions, cash, price_map)
    expos = engine.paperbook.exposures(marks, book_val)

    pnl = round(book_val - capital, 2)
    pnl_pct = round((book_val / capital - 1.0) * 100.0, 2) if capital else 0.0

    curve: List[dict] = []
    stats: dict = {}
    source = "live"
    as_of = None
    track_days = 0

    snaps = strategy_store.snapshot_series(view["id"]) if view.get("id") else []
    if snaps:
        # Audited path: read the persisted daily series instead of recomputing.
        curve = [{"t": s["t"], "nav": s["nav"], "pnl": s["pnl"], "pnlPct": s["pnlPct"]}
                 for s in snaps if s.get("nav") is not None]
        # Track record counts ONLY persisted audited points — never the live
        # overlay below — so promotion can't pass on a not-yet-written day.
        track_days = len(curve)
        # Overlay the current live mark so the desk shows today's value without
        # waiting for the end-of-day write. Display-only: it does not change
        # track_days. Replace today's point if it is already persisted.
        today = date.today().isoformat()
        live_point = {"t": today, "nav": round(book_val, 2), "pnl": pnl, "pnlPct": pnl_pct}
        if curve and curve[-1]["t"] == today:
            curve[-1] = live_point
        else:
            curve.append(live_point)
        stats = engine.paperbook.realized_stats(curve)
        last_src = next((s.get("source") for s in reversed(snaps) if s.get("source")), None)
        source = last_src or "live"
        as_of = strategy_store.latest_snapshot_date(view["id"]) or today
    elif positions and inception:
        # Bootstrap path: reconstruct from real closes until snapshots accrue.
        bulk = repo.price_closes_bulk(syms, days=260)
        curve = engine.paperbook.nav_curve(positions, cash, capital, bulk.get("series", {}), inception)
        stats = engine.paperbook.realized_stats(curve)
        track_days = len(curve)
        source = bulk.get("source") or "live"
        as_of = bulk.get("asOf")

    return {
        "marks": marks,
        "exposures": expos,
        "navCurve": curve,
        "stats": stats,
        "bookValue": round(book_val, 2),
        "capital": capital,
        "cash": round(cash, 2),
        "pnl": pnl,
        "pnlPct": pnl_pct,
        "grossPct": round(sum(abs(e["weight"]) for e in expos), 2),
        "positionsCount": len(positions),
        "ageDays": _age_days(inception),
        "trackDays": track_days,
        "asOf": as_of,
        "source": source,
    }


def _age_days(inception: Optional[str]) -> int:
    if not inception:
        return 0
    try:
        return max(0, (date.today() - date.fromisoformat(inception)).days)
    except ValueError:
        return 0


def record_daily_snapshots(as_of: Optional[date] = None) -> dict:
    """Mark every active (paper/live) book and persist its daily NAV/P&L point.

    Called once per trading day by the background worker. Weekends are skipped so
    the audited series stays on trading days (consistent with the real-close
    reconstruction). Idempotent: re-running on the same day refreshes that day's
    snapshot instead of appending a duplicate.
    """
    day = as_of or date.today()
    if day.weekday() >= 5:  # Saturday/Sunday — no trading day to mark.
        return {"recorded": 0, "skipped": "weekend", "date": day.isoformat()}

    recorded = 0
    skipped = 0
    for s in strategy_store.list_strategies():
        stage = (s.get("stage") or "").lower()
        # Every active (paper/live) book is marked daily — including a flat/empty
        # book, whose NAV is simply its cash so the audited series stays continuous.
        if stage not in ACTIVE_STAGES:
            skipped += 1
            continue
        try:
            m = mark(s)
            strategy_store.record_snapshot(
                s["id"], day.isoformat(),
                nav=m["bookValue"], pnl=m["pnl"], pnl_pct=m["pnlPct"],
                cash=m["cash"], capital=m["capital"], stage=stage,
                source=m.get("source"),
            )
            recorded += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot failed for %s: %s", s.get("id"), exc)
            skipped += 1
    log.info("daily snapshots: recorded %d, skipped %d (%s)", recorded, skipped, day.isoformat())
    return {"recorded": recorded, "skipped": skipped, "date": day.isoformat()}


def evaluate_promotion(view: dict, marked: Optional[dict] = None) -> dict:
    """Check a paper book's realized stats against its promotion criteria."""
    crit = view.get("promotionCriteria") or DEFAULT_CRITERIA
    m = marked or mark(view)
    stats = m.get("stats") or {}
    checks: List[dict] = []

    def add(label: str, ok: bool, detail: str):
        checks.append({"label": label, "pass": bool(ok), "detail": detail})

    sharpe = stats.get("sharpe")
    if "minSharpe" in crit and crit["minSharpe"] is not None:
        ok = sharpe is not None and sharpe >= crit["minSharpe"]
        add(f"Sharpe ≥ {crit['minSharpe']}", ok, f"{sharpe if sharpe is not None else '—'}")
    ret = m.get("pnlPct")
    if "minReturnPct" in crit and crit["minReturnPct"] is not None:
        ok = ret is not None and ret >= crit["minReturnPct"]
        add(f"Return ≥ {crit['minReturnPct']}%", ok, f"{ret}%")
    dd = stats.get("maxDD")
    if "maxDrawdownPct" in crit and crit["maxDrawdownPct"] is not None:
        ok = dd is not None and abs(dd) <= crit["maxDrawdownPct"]
        add(f"Max DD ≤ {crit['maxDrawdownPct']}%", ok, f"{dd if dd is not None else '—'}%")
    # Track record is the count of audited daily NAV points, not calendar age,
    # so promotion rests on a real persisted series rather than inception alone.
    track = m.get("trackDays", m.get("ageDays", 0))
    if "minDays" in crit and crit["minDays"] is not None:
        ok = track >= crit["minDays"]
        add(f"Track record ≥ {crit['minDays']}d", ok, f"{track}d")

    passed = all(c["pass"] for c in checks) if checks else True
    return {"pass": passed, "checks": checks}


def transition(view: dict, to_stage: str, force: bool = False) -> Tuple[dict, bool, str]:
    """Move a strategy to ``to_stage`` with lifecycle + criteria guards.

    Returns (view, ok, message). On a blocked promotion the view is returned
    unchanged with ok=False and an explanatory message.
    """
    to_stage = (to_stage or "").strip().lower()
    cur = (view.get("stage") or "research").lower()
    if to_stage not in ALL_STAGES:
        return view, False, f"Unknown stage '{to_stage}'."
    if to_stage == cur:
        return view, True, f"{view['name']} is already in {cur}."

    # Entering paper (from anywhere short of live) builds/refreshes the book.
    if to_stage == "paper":
        return paper_trade(view), True, f"{view['name']} is now paper-trading."

    # Promotion to live requires a paper book that clears the criteria.
    if to_stage == "live":
        if cur != "paper" and not force:
            return view, False, f"{view['name']} must be paper-trading before going live."
        if not (view.get("positions")):
            view = paper_trade(view)
        ev = evaluate_promotion(view)
        if not ev["pass"] and not force:
            failed = ", ".join(c["label"] for c in ev["checks"] if not c["pass"])
            return view, False, (
                f"{view['name']} does not yet clear its promotion criteria ({failed}). "
                "Say 'force promote' to override."
            )
        return _set_stage(view, "live"), True, f"{view['name']} promoted to live."

    if to_stage == "retired":
        return _set_stage(view, "retired"), True, f"{view['name']} retired."

    # research / backtest are free transitions.
    return _set_stage(view, to_stage), True, f"{view['name']} moved to {to_stage}."


def _set_stage(view: dict, stage: str) -> dict:
    view["stage"] = stage
    history = list(view.get("stageHistory") or [])
    if not history or history[-1].get("stage") != stage:
        history.append({"stage": stage, "at": date.today().isoformat()})
    view["stageHistory"] = history
    return _persist(view)


def demote(view: dict) -> Tuple[dict, bool, str]:
    cur = (view.get("stage") or "research").lower()
    if cur == "live":
        return _set_stage(view, "paper"), True, f"{view['name']} demoted to paper."
    if cur == "paper":
        return _set_stage(view, "backtest"), True, f"{view['name']} demoted to backtest."
    if cur == "backtest":
        return _set_stage(view, "research"), True, f"{view['name']} demoted to research."
    return view, False, f"{view['name']} is in {cur} and cannot be demoted further."


# --------------------------- desk assembly ---------------------------
def desk_payload(selected_key: Optional[str] = None) -> dict:
    """Assemble the desk panel payload: roster of every strategy + a marked
    detail block for the selected (or most relevant) strategy."""
    strategies = strategy_store.list_strategies()
    roster: List[dict] = []
    as_ofs: List[str] = []
    any_live_source = False

    marks_by_id: Dict[str, dict] = {}
    for s in strategies:
        m = mark(s)
        marks_by_id[s["id"]] = m
        if m.get("asOf"):
            as_ofs.append(m["asOf"])
        if m.get("source") == "live":
            any_live_source = True
        roster.append({
            "id": s["id"],
            "name": s["name"],
            "signal": s.get("signal"),
            "signalLabel": engine.signal_label(s.get("signal") or "momentum"),
            "stage": s.get("stage"),
            "positions": m["positionsCount"],
            "grossPct": m["grossPct"],
            "pnl": m["pnl"],
            "pnlPct": m["pnlPct"],
            "sharpe": (m.get("stats") or {}).get("sharpe"),
            "maxDD": (m.get("stats") or {}).get("maxDD"),
            "ageDays": m["ageDays"],
            "bookValue": m["bookValue"],
        })

    selected = None
    if selected_key:
        selected = strategy_store.get_strategy(selected_key)
    if not selected and strategies:
        # Prefer a live/paper book, else the most recent.
        ranked = sorted(
            strategies,
            key=lambda s: (STAGE_ORDER.index(s["stage"]) if s.get("stage") in STAGE_ORDER else -1,
                           s.get("createdAt") or ""),
            reverse=True,
        )
        selected = ranked[0]

    detail = None
    if selected:
        m = marks_by_id.get(selected["id"]) or mark(selected)
        detail = {
            "id": selected["id"],
            "name": selected["name"],
            "signal": selected.get("signal"),
            "signalLabel": engine.signal_label(selected.get("signal") or "momentum"),
            "stage": selected.get("stage"),
            "capital": m["capital"],
            "cash": m["cash"],
            "bookValue": m["bookValue"],
            "pnl": m["pnl"],
            "pnlPct": m["pnlPct"],
            "grossPct": m["grossPct"],
            "ageDays": m["ageDays"],
            "inceptionDate": selected.get("inceptionDate"),
            "universe": (selected.get("construction") or {}).get("universe"),
            "marks": m["marks"],
            "exposures": m["exposures"],
            "navCurve": m["navCurve"],
            "stats": m["stats"],
            "promotionCriteria": selected.get("promotionCriteria"),
            "promotion": evaluate_promotion(selected, m) if selected.get("stage") == "paper" else None,
            "stageHistory": selected.get("stageHistory"),
            "lastRebalance": (selected.get("construction") or {}).get("lastRebalance"),
        }

    return {
        "strategies": roster,
        "selected": detail,
        "stages": ALL_STAGES,
        "count": len(roster),
        "asOf": max(as_ofs) if as_ofs else None,
        "source": "live" if any_live_source else "mock",
    }
