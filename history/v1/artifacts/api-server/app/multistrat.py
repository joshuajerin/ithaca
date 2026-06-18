"""Multi-strategy capital allocation & firm-level risk budgeting.

Treats each paper/live strategy as a *sleeve* of one firm-level book. It:

- aggregates every active (paper/live) sleeve into one combined book — total NAV,
  P&L and firm-level exposures (positions netted by symbol across sleeves);
- measures how the sleeves' returns co-move from their REAL persisted daily NAV
  snapshots (cross-strategy correlation + annualized covariance);
- decomposes firm-level risk (combined vol, per-sleeve contribution to risk,
  concentration) and reports the diversification benefit vs the sum of the
  standalone sleeves;
- recommends how to split capital across the sleeves under a chosen method
  (equal-weight, risk-parity across sleeves, or a target firm-volatility budget),
  showing recommended vs current sleeve weights.

Every risk number is derived from real snapshot history. Sleeves with too little
history (or too little overlap with the others) are flagged and held out of the
risk/allocation math — never imputed. This module is a recommendation / what-if
layer only: it does NOT move capital (that is the rebalancing pipeline's job).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import engine, strategy, strategy_store

log = logging.getLogger(__name__)

TRADING_DAYS = 252
# A sleeve needs at least this many audited NAV points (=> MIN_POINTS-1 daily
# returns) before its standalone risk is trusted in the firm-level math.
MIN_POINTS = 6
# The eligible sleeves must share at least this many overlapping return days for
# the cross-strategy correlation / covariance to be measured honestly.
MIN_COMMON = 5

_METHODS = {
    "equal_weight": "Equal Weight",
    "risk_parity": "Risk Parity",
    "target_risk": "Target Risk Budget",
}
_DEFAULT_TARGET_VOL = 0.10  # 10% annualized firm volatility budget.


def _normalize_method(m: Optional[str]) -> str:
    if not m:
        return "risk_parity"
    key = str(m).lower().strip().replace("-", "_").replace(" ", "_")
    aliases = {
        "equal": "equal_weight", "equalweight": "equal_weight",
        "equal_weighted": "equal_weight", "ew": "equal_weight", "1/n": "equal_weight",
        "naive": "equal_weight",
        "riskparity": "risk_parity", "erc": "risk_parity", "parity": "risk_parity",
        "rp": "risk_parity", "equal_risk": "risk_parity",
        "target": "target_risk", "target_vol": "target_risk",
        "target_volatility": "target_risk", "vol_target": "target_risk",
        "volatility_target": "target_risk", "risk_budget": "target_risk",
        "target_risk_budget": "target_risk", "budget": "target_risk",
    }
    key = aliases.get(key, key)
    return key if key in _METHODS else "risk_parity"


def _active_sleeves() -> List[dict]:
    return [s for s in strategy_store.list_strategies()
            if (s.get("stage") or "").lower() in strategy.ACTIVE_STAGES]


def _returns_by_date(snaps: List[dict]) -> Dict[str, float]:
    """Map each trading date to that day's NAV return (from the audited series)."""
    navs = [(s["t"], float(s["nav"])) for s in snaps
            if s.get("nav") is not None and s.get("t")]
    navs.sort(key=lambda x: x[0])
    out: Dict[str, float] = {}
    for (t0, n0), (t1, n1) in zip(navs, navs[1:]):
        if n0 > 0:
            out[t1] = n1 / n0 - 1.0
    return out


def _largest_aligned(
    rets: List[Tuple[int, Dict[str, float]]]
) -> Tuple[List[int], List[str], List[int]]:
    """Pick the biggest subset of sleeves with >= MIN_COMMON shared return days.

    Returns ``(used_idx, dates, dropped_idx)``. Sleeves are dropped shortest-first
    when the common window is too thin, so a brand-new sleeve that barely overlaps
    the others is flagged rather than shrinking everyone's history.
    """
    items = sorted(rets, key=lambda x: len(x[1]), reverse=True)
    dropped: List[int] = []
    while len(items) >= 2:
        common = set(items[0][1].keys())
        for _, d in items[1:]:
            common &= set(d.keys())
        if len(common) >= MIN_COMMON:
            return [i for i, _ in items], sorted(common), dropped
        dropped.append(items[-1][0])
        items = items[:-1]
    return [], [], dropped + [i for i, _ in items]


def _firm_curve(active: List[Tuple[dict, List[dict]]]) -> List[dict]:
    """Combined firm NAV over the union of dates (a sleeve contributes only from
    its own first snapshot onward; its last known NAV is carried forward)."""
    per: List[Tuple[str, Dict[str, float]]] = []
    all_dates: set = set()
    for _sl, snaps in active:
        m: Dict[str, float] = {}
        for s in snaps:
            if s.get("nav") is not None and s.get("t"):
                m[s["t"]] = float(s["nav"])
        if m:
            per.append((min(m.keys()), m))
            all_dates.update(m.keys())
    if not all_dates:
        return []
    dates = sorted(all_dates)
    last = [None] * len(per)
    curve: List[dict] = []
    for d in dates:
        total = 0.0
        live = False
        for i, (first, m) in enumerate(per):
            if d in m:
                last[i] = m[d]
            if d >= first and last[i] is not None:
                total += last[i]
                live = True
        if live:
            curve.append({"t": d, "nav": round(total, 2)})
    return curve


def _aggregate_exposures(marks_by_id: Dict[str, List[dict]], book_val: float) -> List[dict]:
    """Net firm-level exposures by symbol across every sleeve's marked positions."""
    by_sym: Dict[str, float] = {}
    for marks in marks_by_id.values():
        for m in marks:
            by_sym[m["symbol"]] = by_sym.get(m["symbol"], 0.0) + float(m.get("marketValue") or 0.0)
    if book_val <= 0:
        return []
    rows = [{"symbol": s, "marketValue": round(v, 2), "weight": round(v / book_val * 100.0, 2)}
            for s, v in by_sym.items()]
    rows.sort(key=lambda r: abs(r["weight"]), reverse=True)
    return rows


def firm_payload(method: Optional[str] = None, target_vol: Optional[float] = None) -> dict:
    """Assemble the multi-strategy allocation + firm-risk panel payload."""
    method = _normalize_method(method)
    tgt = float(target_vol) if target_vol else _DEFAULT_TARGET_VOL
    if tgt > 1.0:  # accept a percentage like 12 for 12%.
        tgt = tgt / 100.0
    tgt = float(np.clip(tgt, 0.01, 0.60))

    sleeves = _active_sleeves()
    methods_meta = [{"id": k, "label": v} for k, v in _METHODS.items()]

    if not sleeves:
        return {
            "sleeves": [], "combined": None, "correlation": None, "risk": None,
            "allocation": None, "excluded": [], "firmCurve": [],
            "methods": methods_meta, "method": method, "methodLabel": _METHODS[method],
            "count": 0,
            "note": "No paper or live strategies yet — create and paper-trade a few "
                    "strategies, then allocate capital across them as sleeves.",
            "asOf": None, "source": "mock",
        }

    marks_by_id: Dict[str, List[dict]] = {}
    snaps_active: List[Tuple[dict, List[dict]]] = []
    sleeve_rows: List[dict] = []
    ret_dicts: List[Tuple[int, Dict[str, float]]] = []
    as_ofs: List[str] = []
    any_live = False

    combined_nav = 0.0
    combined_capital = 0.0
    combined_pnl = 0.0

    for idx, s in enumerate(sleeves):
        m = strategy.mark(s)
        marks_by_id[s["id"]] = m.get("marks") or []
        snaps = strategy_store.snapshot_series(s["id"])
        snaps_active.append((s, snaps))
        if m.get("asOf"):
            as_ofs.append(m["asOf"])
        if m.get("source") == "live":
            any_live = True

        combined_nav += float(m["bookValue"])
        combined_capital += float(m["capital"])
        combined_pnl += float(m["pnl"])

        rd = _returns_by_date(snaps)
        n_points = len({s["t"] for s in snaps if s.get("nav") is not None and s.get("t")})
        eligible = n_points >= MIN_POINTS and len(rd) >= MIN_POINTS - 1
        if eligible:
            ret_dicts.append((idx, rd))

        sleeve_rows.append({
            "id": s["id"],
            "name": s["name"],
            "stage": s.get("stage"),
            "signalLabel": engine.signal_label(s.get("signal") or "momentum"),
            "capital": m["capital"],
            "bookValue": m["bookValue"],
            "pnl": m["pnl"],
            "pnlPct": m["pnlPct"],
            "points": n_points,
            "eligible": eligible,
            # filled in below for the used (eligible + overlapping) set:
            "weight": None, "vol": None, "riskContribPct": None,
            "current": None, "recommended": None, "delta": None,
        })

    row_by_idx = {i: sleeve_rows[i] for i in range(len(sleeve_rows))}

    combined_pnl_pct = round((combined_nav / combined_capital - 1.0) * 100.0, 2) if combined_capital else 0.0
    firm_expos = _aggregate_exposures(marks_by_id, combined_nav)
    gross_pct = round(sum(abs(e["weight"]) for e in firm_expos), 2)
    combined = {
        "nav": round(combined_nav, 2),
        "capital": round(combined_capital, 2),
        "pnl": round(combined_pnl, 2),
        "pnlPct": combined_pnl_pct,
        "grossPct": gross_pct,
        "exposures": firm_expos[:14],
        "exposureCount": len(firm_expos),
        "sleeveCount": len(sleeves),
    }

    excluded: List[dict] = []
    for i, row in enumerate(sleeve_rows):
        if not row["eligible"]:
            excluded.append({
                "name": row["name"],
                "reason": f"only {row['points']} day(s) of NAV history (need {MIN_POINTS})",
            })

    used_idx, common_dates, dropped_idx = _largest_aligned(ret_dicts)
    for di in dropped_idx:
        excluded.append({
            "name": row_by_idx[di]["name"],
            "reason": f"too little overlap with the other sleeves (need {MIN_COMMON} shared days)",
        })

    correlation = None
    risk = None
    allocation = None

    if used_idx:
        rd_by_idx = dict(ret_dicts)
        names = [row_by_idx[i]["name"] for i in used_idx]
        # Aligned daily-return matrix (n_used x T) over the shared window.
        R = np.array([[rd_by_idx[i][d] for d in common_dates] for i in used_idx], dtype=float)
        cov = np.atleast_2d(np.cov(R)) * TRADING_DAYS  # annualized sleeve covariance
        vols = np.sqrt(np.clip(np.diag(cov), 0.0, None))

        # Current firm weights restricted to the used (investable) set.
        bvs = np.array([float(row_by_idx[i]["bookValue"]) for i in used_idx], dtype=float)
        w_cur = bvs / bvs.sum() if bvs.sum() > 0 else np.full(len(used_idx), 1.0 / len(used_idx))

        for col, i in enumerate(used_idx):
            row_by_idx[i]["vol"] = round(float(vols[col]) * 100.0, 2)

        # Correlation (only meaningful with >= 2 sleeves).
        if len(used_idx) >= 2:
            corr = np.atleast_2d(np.corrcoef(R))
            matrix = [[round(float(corr[a][b]), 2) for b in range(len(used_idx))]
                      for a in range(len(used_idx))]
            correlation = {"names": names, "matrix": matrix, "days": len(common_dates)}

        # Firm-level risk at the CURRENT weights.
        cur_vol = float(np.sqrt(max(w_cur @ cov @ w_cur, 0.0)))
        weighted_avg_vol = float(w_cur @ vols)
        rc = engine.risk_contributions(w_cur, cov)  # % of total risk per sleeve
        for col, i in enumerate(used_idx):
            row_by_idx[i]["riskContribPct"] = round(float(rc[col]), 2)
            row_by_idx[i]["current"] = round(float(w_cur[col]) * 100.0, 2)
        hhi = float(np.sum(w_cur ** 2))
        risk = {
            "combinedVol": round(cur_vol * 100.0, 2),
            "weightedAvgVol": round(weighted_avg_vol * 100.0, 2),
            "diversificationBenefit": round((weighted_avg_vol - cur_vol) * 100.0, 2),
            "diversificationRatio": round(weighted_avg_vol / cur_vol, 2) if cur_vol > 1e-9 else 1.0,
            "concentrationHHI": round(hhi, 3),
            "effectiveSleeves": round(1.0 / hhi, 2) if hhi > 0 else float(len(used_idx)),
            "window": len(common_dates),
        }

        # Recommended allocation across the used sleeves.
        n = len(used_idx)
        leverage = None
        if method == "equal_weight":
            w_rec = np.full(n, 1.0 / n)
        elif method == "target_risk":
            base = engine.risk_parity(cov) if n > 1 else np.ones(1)
            base_vol = float(np.sqrt(max(base @ cov @ base, 0.0)))
            k = tgt / base_vol if base_vol > 1e-9 else 1.0
            w_rec = base * k
            leverage = round(float(w_rec.sum()), 3)
        else:  # risk_parity
            w_rec = engine.risk_parity(cov) if n > 1 else np.ones(1)

        rec_vol = float(np.sqrt(max(w_rec @ cov @ w_rec, 0.0)))
        rec_rc = engine.risk_contributions(w_rec, cov)
        rows_alloc: List[dict] = []
        for col, i in enumerate(used_idx):
            cur = float(w_cur[col]) * 100.0
            rec = float(w_rec[col]) * 100.0
            row_by_idx[i]["recommended"] = round(rec, 2)
            row_by_idx[i]["delta"] = round(rec - cur, 2)
            rows_alloc.append({
                "name": row_by_idx[i]["name"],
                "stage": row_by_idx[i]["stage"],
                "current": round(cur, 2),
                "recommended": round(rec, 2),
                "delta": round(rec - cur, 2),
                "vol": row_by_idx[i]["vol"],
                "recRiskContribPct": round(float(rec_rc[col]), 2),
            })
        allocation = {
            "method": method,
            "methodLabel": _METHODS[method],
            "rows": rows_alloc,
            "recommendedVol": round(rec_vol * 100.0, 2),
            "currentVol": round(cur_vol * 100.0, 2),
            "targetVol": round(tgt * 100.0, 2) if method == "target_risk" else None,
            "leverage": leverage,
            "investableSleeves": n,
        }

    return {
        "sleeves": sleeve_rows,
        "combined": combined,
        "correlation": correlation,
        "risk": risk,
        "allocation": allocation,
        "excluded": excluded,
        "firmCurve": _firm_curve(snaps_active),
        "methods": methods_meta,
        "method": method,
        "methodLabel": _METHODS[method],
        "count": len(sleeves),
        "note": None if used_idx else (
            "Not enough audited NAV history yet to measure cross-strategy risk — "
            f"sleeves need {MIN_POINTS} daily snapshots (and {MIN_COMMON} overlapping "
            "days) before capital can be allocated by risk. The combined book is shown."
        ),
        "asOf": max(as_ofs) if as_ofs else None,
        "source": "live" if any_live else "mock",
    }
