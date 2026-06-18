"""Pre-trade risk & compliance gate (pure, deterministic).

Given a proposed/resulting book expressed as signed NAV-fraction weights plus a
limit configuration, restricted/watch lists and the kill-switch state, decide
whether a trade list is allowed *before* it is applied to a book. No IO — the
caller (the strategy service / skill builder) owns sourcing the weights, the
persisted config and the audit write; this module only does the maths and the
pass/fail logic so it stays unit-testable in isolation.

Four limit families (mirroring the desk language in the task):
  * position    — max single-name absolute weight.
  * exposure    — max net exposure (signed sum of weights).
  * leverage    — max gross exposure (sum of absolute weights) as a multiple.
  * concentration — combined absolute weight of the largest ``CONCENTRATION_N``
                    names.

Plus two list checks and the kill switch:
  * restricted  — any name in the resulting book is a HARD block.
  * watch       — any name in the resulting book is a soft warning (allowed).
  * kill switch — a global or per-strategy halt that blocks every trade.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

# Number of largest names summed for the concentration check.
CONCENTRATION_N = 5

# Fraction of a limit at/above which a still-passing check is flagged "warn".
WARN_BAND = 0.9

# Default firm limits. Percent fields are % of NAV; leverage is a multiple.
DEFAULT_LIMITS: Dict[str, float] = {
    "maxPositionPct": 15.0,        # per-name absolute weight
    "maxNetPct": 120.0,            # net exposure (signed sum)
    "maxLeverage": 2.0,            # gross exposure / NAV
    "maxConcentrationPct": 50.0,   # top-N absolute weight
}

# Editor metadata so the UI can render and label the limit controls.
LIMIT_DEFS: List[dict] = [
    {"key": "maxPositionPct", "label": "Max position", "unit": "%",
     "help": "Largest absolute weight allowed in any single name."},
    {"key": "maxNetPct", "label": "Max net exposure", "unit": "%",
     "help": "Cap on the net (long minus short) exposure of the book."},
    {"key": "maxLeverage", "label": "Max leverage", "unit": "x",
     "help": "Gross exposure (sum of absolute weights) as a multiple of NAV."},
    {"key": "maxConcentrationPct", "label": "Max concentration", "unit": "%",
     "help": f"Combined absolute weight of the {CONCENTRATION_N} largest names."},
]


def merge_limits(overrides: Optional[dict]) -> Dict[str, float]:
    """Return DEFAULT_LIMITS with any non-null overrides applied."""
    out = dict(DEFAULT_LIMITS)
    if overrides:
        for k, v in overrides.items():
            if k in out and v is not None:
                try:
                    out[k] = float(v)
                except (TypeError, ValueError):
                    continue
    return out


def _clean_weights(weights: Dict[str, float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for s, w in (weights or {}).items():
        sym = (s or "").upper()
        if not sym:
            continue
        try:
            fw = float(w)
        except (TypeError, ValueError):
            continue
        if abs(fw) < 1e-9:
            continue
        out[sym] = out.get(sym, 0.0) + fw
    return out


def book_metrics(weights: Dict[str, float]) -> dict:
    """Gross/net/max-position/concentration for a signed-weight book (fractions).

    All percent figures are returned in percent (0.15 -> 15.0); leverage is a
    multiple. ``topNames`` lists the names driving the concentration figure.
    """
    w = _clean_weights(weights)
    if not w:
        return {
            "gross": 0.0, "net": 0.0, "leverage": 0.0,
            "maxPositionPct": 0.0, "maxPositionName": None,
            "concentrationPct": 0.0, "topNames": [], "names": 0,
        }
    gross = sum(abs(x) for x in w.values())
    net = sum(w.values())
    max_name, max_abs = max(w.items(), key=lambda kv: abs(kv[1]))
    ranked = sorted(w.items(), key=lambda kv: abs(kv[1]), reverse=True)
    top = ranked[:CONCENTRATION_N]
    concentration = sum(abs(v) for _, v in top)
    return {
        "gross": round(gross, 6),
        "net": round(net, 6),
        "leverage": round(gross, 6),  # gross / NAV; NAV is 1.0 in weight space
        "maxPositionPct": round(abs(max_abs) * 100.0, 4),
        "maxPositionName": max_name,
        "concentrationPct": round(concentration * 100.0, 4),
        "topNames": [s for s, _ in top],
        "names": len(w),
    }


def _status(value: float, limit: float) -> Tuple[str, float]:
    """Return (status, utilization) for a value against an upper-bound limit."""
    if limit <= 0:
        return ("ok", 0.0)
    util = value / limit
    if util > 1.0 + 1e-9:
        return ("breach", util)
    if util >= WARN_BAND:
        return ("warn", util)
    return ("ok", util)


def evaluate_limits(weights: Dict[str, float], limits: Optional[dict] = None) -> List[dict]:
    """One check row per limit family. Each row carries the config ``key`` so the
    UI can map it back, the measured ``value``, the ``limit`` and a status."""
    lim = merge_limits(limits)
    m = book_metrics(weights)
    rows: List[dict] = []

    pos_status, pos_util = _status(m["maxPositionPct"], lim["maxPositionPct"])
    rows.append({
        "key": "maxPositionPct", "label": "Max position", "unit": "%",
        "value": m["maxPositionPct"], "limit": lim["maxPositionPct"],
        "status": pos_status, "utilization": round(pos_util, 4),
        "detail": (f"{m['maxPositionName']} at {m['maxPositionPct']:.1f}%"
                   if m["maxPositionName"] else "no positions"),
    })

    net_pct = abs(m["net"]) * 100.0
    net_status, net_util = _status(net_pct, lim["maxNetPct"])
    rows.append({
        "key": "maxNetPct", "label": "Net exposure", "unit": "%",
        "value": round(net_pct, 4), "limit": lim["maxNetPct"],
        "status": net_status, "utilization": round(net_util, 4),
        "detail": f"net {m['net'] * 100.0:.1f}% of NAV",
    })

    lev_status, lev_util = _status(m["leverage"], lim["maxLeverage"])
    rows.append({
        "key": "maxLeverage", "label": "Leverage", "unit": "x",
        "value": round(m["leverage"], 4), "limit": lim["maxLeverage"],
        "status": lev_status, "utilization": round(lev_util, 4),
        "detail": f"gross {m['gross'] * 100.0:.0f}% of NAV",
    })

    conc_status, conc_util = _status(m["concentrationPct"], lim["maxConcentrationPct"])
    rows.append({
        "key": "maxConcentrationPct", "label": "Concentration", "unit": "%",
        "value": m["concentrationPct"], "limit": lim["maxConcentrationPct"],
        "status": conc_status, "utilization": round(conc_util, 4),
        "detail": f"top {min(CONCENTRATION_N, m['names'])} = {m['concentrationPct']:.1f}%",
    })
    return rows


def _norm_list(items: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for it in items or []:
        s = (it or "").strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def evaluate_lists(
    symbols: Sequence[str],
    restricted: Optional[Sequence[str]] = None,
    watch: Optional[Sequence[str]] = None,
) -> Tuple[List[str], List[str]]:
    """Return (restrictedHits, watchHits) — names in ``symbols`` that appear on
    each list, preserving the book's ordering."""
    syms = _norm_list(symbols)
    rset = set(_norm_list(restricted))
    wset = set(_norm_list(watch))
    restricted_hits = [s for s in syms if s in rset]
    watch_hits = [s for s in syms if s in wset]
    return restricted_hits, watch_hits


def evaluate_gate(
    *,
    weights: Dict[str, float],
    limits: Optional[dict] = None,
    restricted: Optional[Sequence[str]] = None,
    watch: Optional[Sequence[str]] = None,
    kill_switch: bool = False,
    kill_reason: Optional[str] = None,
) -> dict:
    """Full pre-trade gate over a resulting book.

    Returns a structured decision. ``ok`` is True only when there are NO hard
    violations (limit breach, restricted name, or kill switch). Warn-band limits
    and watch-list names are reported but do not block.
    """
    w = _clean_weights(weights)
    checks = evaluate_limits(w, limits)
    restricted_hits, watch_hits = evaluate_lists(list(w.keys()), restricted, watch)

    violations: List[str] = []
    warnings: List[str] = []

    if kill_switch:
        violations.append(
            "Kill switch is engaged" + (f": {kill_reason}" if kill_reason else "")
        )

    for c in checks:
        if c["status"] == "breach":
            violations.append(
                f"{c['label']} {c['value']:.1f}{c['unit']} exceeds the "
                f"{c['limit']:.1f}{c['unit']} limit"
            )
        elif c["status"] == "warn":
            warnings.append(
                f"{c['label']} at {c['utilization'] * 100:.0f}% of its limit"
            )

    if restricted_hits:
        violations.append(
            "Restricted name(s) in the book: " + ", ".join(restricted_hits)
        )
    if watch_hits:
        warnings.append("Watch-list name(s): " + ", ".join(watch_hits))

    ok = not violations
    reason = None if ok else "; ".join(violations)
    return {
        "ok": ok,
        "blocked": not ok,
        "metrics": book_metrics(w),
        "checks": checks,
        "violations": violations,
        "warnings": warnings,
        "restricted": restricted_hits,
        "watch": watch_hits,
        "killSwitch": bool(kill_switch),
        "killReason": kill_reason if kill_switch else None,
        "reason": reason,
    }
