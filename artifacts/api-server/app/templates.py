"""Strategy Templates Marketplace.

A browsable catalog of pre-built, parameterized strategy templates. Each template
is a preset of an alpha **signal** (momentum / value / quality / low volatility /
short-term reversal) plus an optional **sector** universe and a target **holdings**
count / **capital** size. Users can:

- browse the catalog (built-in templates + their own saved ones),
- preview a template — a real backtest of the signal's top-quantile book via the
  shared ``build_signal_portfolio`` engine (Sharpe, CAGR, drawdown vs benchmark),
- tweak its parameters (signal, sector, holdings, capital),
- clone a configured template into the paper-trading strategy desk
  (``strategy.create_strategy`` → diversified, compliance-checked paper book),
- save a configured template as a reusable preset.

This module owns no persistence of its own beyond ``template_store`` (user
templates); built-in templates are defined inline.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from . import engine, repo, skills, strategy, template_store

log = logging.getLogger(__name__)

DEFAULT_TOP_N = 10
MIN_TOP_N = 5
MAX_TOP_N = 30
DEFAULT_CAPITAL = 1_000_000.0


# Built-in catalog. ``sector`` is a free-text sector name (resolved against the
# universe) or None for the broad large-cap cross-section. ``topN`` / ``capital``
# configure the cloned paper book; the preview backtests the signal's top quantile.
_BUILT_IN: List[dict] = [
    {
        "id": "builtin-momentum-leaders",
        "name": "Momentum Leaders",
        "description": "Owns the strongest 3-month trending names across the large-cap "
                       "universe — a classic price-momentum tilt.",
        "category": "Momentum",
        "signal": "momentum",
        "sector": None,
        "topN": 10,
        "capital": 1_000_000.0,
    },
    {
        "id": "builtin-tech-momentum",
        "name": "Tech Momentum",
        "description": "Price momentum concentrated in the technology sector — rides "
                       "leadership in the highest-beta corner of the market.",
        "category": "Momentum",
        "signal": "momentum",
        "sector": "Technology",
        "topN": 8,
        "capital": 1_000_000.0,
    },
    {
        "id": "builtin-deep-value",
        "name": "Deep Value",
        "description": "Buys the cheapest names by earnings yield (1 / P·E) — a "
                       "contrarian value tilt that leans into out-of-favour stocks.",
        "category": "Value",
        "signal": "value",
        "sector": None,
        "topN": 12,
        "capital": 1_000_000.0,
    },
    {
        "id": "builtin-quality-compounders",
        "name": "Quality Compounders",
        "description": "Holds the most profitable names by net margin — a quality "
                       "tilt toward durable, high-margin businesses.",
        "category": "Quality",
        "signal": "quality",
        "sector": None,
        "topN": 12,
        "capital": 1_000_000.0,
    },
    {
        "id": "builtin-low-volatility",
        "name": "Low Volatility Defensive",
        "description": "Tilts to the calmest names by trailing 1-month realized vol — "
                       "the low-volatility anomaly, aiming for a smoother ride.",
        "category": "Defensive",
        "signal": "low_volatility",
        "sector": None,
        "topN": 15,
        "capital": 1_000_000.0,
    },
    {
        "id": "builtin-mean-reversion",
        "name": "Short-Term Reversal",
        "description": "Buys the biggest 2-week losers expecting a bounce — a "
                       "short-horizon mean-reversion tilt.",
        "category": "Mean Reversion",
        "signal": "short_reversal",
        "sector": None,
        "topN": 10,
        "capital": 1_000_000.0,
    },
]


# --------------------------- helpers ---------------------------
def _clean_sector(sector) -> Optional[str]:
    """Normalize a sector value: empty / 'all' / 'any' means the broad universe."""
    if sector is None:
        return None
    s = str(sector).strip()
    if s == "" or s.lower() in ("all", "any", "all sectors", "broad", "universe"):
        return None
    return s


def _clamp_topn(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = DEFAULT_TOP_N
    return max(MIN_TOP_N, min(MAX_TOP_N, n))


def _clean_capital(value) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        c = DEFAULT_CAPITAL
    return c if c > 0 else DEFAULT_CAPITAL


def _normalize_template(raw: dict, built_in: bool) -> dict:
    """Shape a stored/built-in record into the canonical catalog entry."""
    signal = engine.normalize_signal(raw.get("signal") or "momentum")
    meta = engine.SIGNAL_META.get(signal, {})
    params = raw.get("params") or {}
    sector = _clean_sector(raw.get("sector") if raw.get("sector") is not None else params.get("sector"))
    return {
        "id": raw.get("id"),
        "name": raw.get("name") or engine.signal_label(signal),
        "description": raw.get("description") or meta.get("desc", ""),
        "category": raw.get("category") or meta.get("label", "Strategy"),
        "signal": signal,
        "signalLabel": meta.get("label", signal),
        "sector": sector,
        "topN": _clamp_topn(raw.get("topN", params.get("topN", DEFAULT_TOP_N))),
        "capital": _clean_capital(raw.get("capital", params.get("capital", DEFAULT_CAPITAL))),
        "builtIn": built_in,
    }


def list_all() -> List[dict]:
    """Built-in templates followed by the user's saved templates."""
    out = [_normalize_template(t, True) for t in _BUILT_IN]
    for t in template_store.list_templates():
        out.append(_normalize_template(t, False))
    return out


def get(template_id: str) -> Optional[dict]:
    if not template_id:
        return None
    for t in _BUILT_IN:
        if t["id"] == template_id:
            return _normalize_template(t, True)
    stored = template_store.get_template(template_id)
    return _normalize_template(stored, False) if stored else None


def signal_options() -> List[dict]:
    """Pickable signals for the in-panel tweak control."""
    return [
        {"id": key, "label": meta.get("label", key), "desc": meta.get("desc", "")}
        for key, meta in engine.SIGNAL_META.items()
    ]


def sector_options() -> List[dict]:
    """Sectors available as universe filters (plus the broad-universe option)."""
    out = [{"id": "", "name": "All sectors"}]
    try:
        for sec in repo.list_sectors():
            sid = sec.get("id") or sec.get("name")
            name = sec.get("name") or sid
            if sid:
                out.append({"id": str(name), "name": str(name)})
    except Exception as exc:  # noqa: BLE001
        log.warning("sector_options failed: %s", exc)
    return out


def resolve_config(params: dict) -> dict:
    """Resolve the focused template config: start from a template (by id) and
    overlay any explicit tweaks (signal / sector / topN / capital / name)."""
    base: Optional[dict] = None
    tid = params.get("templateId") or params.get("id")
    if tid:
        base = get(tid)
    if base is None:
        catalog = list_all()
        base = catalog[0] if catalog else _normalize_template(_BUILT_IN[0], True)

    cfg = dict(base)
    if params.get("signal"):
        sig = engine.normalize_signal(params["signal"])
        cfg["signal"] = sig
        cfg["signalLabel"] = engine.SIGNAL_META.get(sig, {}).get("label", sig)
    if "sector" in params:
        cfg["sector"] = _clean_sector(params.get("sector"))
    if params.get("topN") is not None:
        cfg["topN"] = _clamp_topn(params.get("topN"))
    if params.get("capital") is not None:
        cfg["capital"] = _clean_capital(params.get("capital"))
    if params.get("name"):
        cfg["name"] = str(params["name"]).strip()[:60]
    return cfg


def _downsample(curve: List[dict], cap: int = 180) -> List[dict]:
    if not curve or len(curve) <= cap:
        return curve
    step = len(curve) / cap
    out = [curve[int(i * step)] for i in range(cap)]
    if out[-1] is not curve[-1]:
        out.append(curve[-1])
    return out


def preview(cfg: dict) -> Tuple[Optional[dict], Optional[str]]:
    """Backtest the template's signal as a top-quantile book (real data).

    Returns ``(preview, error)`` — exactly one is non-None. The preview reuses the
    shared ``build_signal_portfolio`` engine so stats are identical to the Signal
    Portfolio desk (Sharpe, CAGR, drawdown vs an equal-weight benchmark).
    """
    try:
        pf = skills.build_signal_portfolio({
            "signal": cfg["signal"],
            "sector": cfg.get("sector"),
            "scheme": "top_quantile",
        })
    except Exception as exc:  # noqa: BLE001
        return None, str(exc) or "could not preview this template"

    holdings = [
        {"symbol": h.get("symbol"), "name": h.get("name"), "weight": h.get("weight")}
        for h in (pf.get("holdings") or [])[: cfg.get("topN", DEFAULT_TOP_N)]
    ]
    prev = {
        "stats": pf.get("stats") or {},
        "benchStats": pf.get("benchStats") or {},
        "curve": _downsample(pf.get("curve") or []),
        "drawdown": _downsample(pf.get("drawdown") or []),
        "universe": pf.get("universe"),
        "universeSize": pf.get("universeSize"),
        "included": pf.get("included"),
        "excluded": pf.get("excluded"),
        "holding": pf.get("holding"),
        "turnoverAnnual": pf.get("turnoverAnnual"),
        "holdings": holdings,
        "scheme": "top_quantile",
        "schemeLabel": pf.get("schemeLabel"),
        "source": pf.get("source", "mock"),
        "asOf": pf.get("asOf"),
    }
    return prev, None


def clone(cfg: dict) -> dict:
    """Clone a configured template into the paper-trading desk.

    Builds the signal's top-N book and registers it as a paper strategy via
    ``strategy.create_strategy`` (which runs the pre-trade compliance gate). The
    top-N book is diversified (equal weight ≤ 1/N) so it clears the concentration
    limit; if a violation still occurs the caller surfaces the ComplianceBlock.
    """
    signal = engine.normalize_signal(cfg["signal"])
    sector = _clean_sector(cfg.get("sector"))
    top_n = _clamp_topn(cfg.get("topN", DEFAULT_TOP_N))
    capital = _clean_capital(cfg.get("capital", DEFAULT_CAPITAL))
    name = (cfg.get("name") or "").strip() or f"{engine.signal_label(signal)} Template"

    # Size the book to the template's holdings count by deriving the top-N weights
    # explicitly, then passing them through so the desk book matches the preview's
    # signal tilt at the requested breadth.
    wmap, _picks, excluded, label = strategy.derive_target_weights(
        signal, None, None, sector, top_n=top_n,
    )
    if not wmap:
        raise ValueError("no tradeable names for this template's universe")
    symbols = list(wmap.keys())
    weights = list(wmap.values())

    cons = {
        "source": "template",
        "templateId": cfg.get("id"),
        "templateName": cfg.get("name"),
        "universe": label,
    }
    if excluded:
        cons["excluded"] = excluded

    view = strategy.create_strategy(
        name=name, signal=signal, symbols=symbols, weights=weights,
        construction=cons, capital=capital, paper=True,
    )
    return view


def save(cfg: dict) -> dict:
    """Persist a user-configured template as a reusable preset."""
    import uuid

    signal = engine.normalize_signal(cfg.get("signal") or "momentum")
    meta = engine.SIGNAL_META.get(signal, {})
    name = (cfg.get("name") or "").strip() or f"My {engine.signal_label(signal)}"
    sector = _clean_sector(cfg.get("sector"))
    top_n = _clamp_topn(cfg.get("topN", DEFAULT_TOP_N))
    capital = _clean_capital(cfg.get("capital", DEFAULT_CAPITAL))

    record = {
        "id": f"user-{uuid.uuid4().hex[:12]}",
        "name": name,
        "description": (cfg.get("description") or "").strip()
                       or f"Saved {meta.get('label', signal)} preset.",
        "category": cfg.get("category") or "Saved",
        "signal": signal,
        "sector": sector,
        "params": {"topN": top_n, "capital": capital},
    }
    saved = template_store.upsert(record)
    return _normalize_template(saved, False)
