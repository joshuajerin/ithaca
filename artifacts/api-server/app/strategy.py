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

from . import engine, repo, strategy_store

log = logging.getLogger(__name__)

DEFAULT_CAPITAL = 1_000_000.0
DEFAULT_TOP_N = 8
_UNIVERSE_CAP = 40

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

    view["positions"] = positions
    view["cash"] = cash
    view["inceptionDate"] = date.today().isoformat()
    history = list(view.get("stageHistory") or [])
    if not history or history[-1].get("stage") != "paper":
        history.append({"stage": "paper", "at": date.today().isoformat()})
    view["stageHistory"] = history
    view["stage"] = "paper"
    return _persist(view)


def mark(view: dict) -> dict:
    """Mark the book to market and reconstruct its real P&L history."""
    positions = view.get("positions") or []
    cash = float(view.get("cash") or 0.0)
    capital = float(view.get("capital") or DEFAULT_CAPITAL)
    inception = view.get("inceptionDate")

    syms = [p["symbol"] for p in positions]
    price_map = _price_map(syms)
    marks = engine.paperbook.position_marks(positions, price_map)
    book_val = engine.paperbook.book_value(positions, cash, price_map)
    expos = engine.paperbook.exposures(marks, book_val)

    curve: List[dict] = []
    stats: dict = {}
    source = "live"
    as_of = None
    if positions and inception:
        bulk = repo.price_closes_bulk(syms, days=260)
        curve = engine.paperbook.nav_curve(positions, cash, capital, bulk.get("series", {}), inception)
        stats = engine.paperbook.realized_stats(curve)
        source = bulk.get("source") or "live"
        as_of = bulk.get("asOf")

    pnl = round(book_val - capital, 2)
    pnl_pct = round((book_val / capital - 1.0) * 100.0, 2) if capital else 0.0
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
    age = m.get("ageDays", 0)
    if "minDays" in crit and crit["minDays"] is not None:
        ok = age >= crit["minDays"]
        add(f"Track record ≥ {crit['minDays']}d", ok, f"{age}d")

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
        }

    return {
        "strategies": roster,
        "selected": detail,
        "stages": ALL_STAGES,
        "count": len(roster),
        "asOf": max(as_ofs) if as_ofs else None,
        "source": "live" if any_live_source else "mock",
    }
