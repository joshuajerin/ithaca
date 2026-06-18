"""Reusable period-return computation from a price series.

Every widget that shows performance should label its timeframe explicitly. The
canonical *day* change lives on the company quote (`changePct`); genuine period
returns (1M / YTD / 1Y) are derived here from the OHLCV close series so they are
never confused with the 1-day move.

Pure and dependency-free so it is trivially unit-testable: it operates on a list
of ``{"t": iso_date, "c": close}`` points (oldest -> newest) and returns a map of
window -> percentage return (or ``None`` when there is not enough history).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

# Calendar-day lookbacks for fixed windows. YTD is handled separately (anchored
# to the prior year-end close).
WINDOW_DAYS = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}

DEFAULT_WINDOWS = ("1M", "YTD", "1Y")


def _parse_date(t: str) -> Optional[date]:
    if not t:
        return None
    try:
        return date.fromisoformat(str(t)[:10])
    except ValueError:
        return None


def _close_on_or_before(points: Sequence[dict], target: date) -> Optional[dict]:
    """Last point whose date is on or before ``target`` (points are sorted)."""
    chosen = None
    for p in points:
        d = _parse_date(p.get("t"))
        if d is None:
            continue
        if d <= target:
            chosen = p
        else:
            break
    return chosen


def compute_period_returns(
    points: Sequence[dict],
    windows: Sequence[str] = DEFAULT_WINDOWS,
    last: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Return ``{window: pct_return}`` computed from the close series.

    A window is ``None`` when there isn't enough history to anchor it (e.g. a
    series shorter than the lookback), so callers can render "—" rather than a
    misleading figure.
    """
    out: Dict[str, Optional[float]] = {w: None for w in windows}
    pts = [p for p in points if p.get("c")]
    if not pts:
        return out

    last_c = float(last) if last is not None else float(pts[-1]["c"])
    last_date = _parse_date(pts[-1].get("t"))
    if last_date is None:
        return out
    first_date = _parse_date(pts[0].get("t"))

    for w in windows:
        if w == "1D":
            ref = float(pts[-2]["c"]) if len(pts) >= 2 else None
        elif w == "YTD":
            target = date(last_date.year - 1, 12, 31)
            ref_pt = _close_on_or_before(pts, target)
            if ref_pt is None:
                # No data before this year: anchor to the earliest in-year close.
                in_year = [p for p in pts if (_parse_date(p.get("t")) or last_date).year == last_date.year]
                ref_pt = in_year[0] if in_year else pts[0]
            ref = float(ref_pt["c"]) if ref_pt else None
        else:
            days = WINDOW_DAYS.get(w)
            if days is None:
                ref = None
            else:
                target = last_date - timedelta(days=days)
                # Only report the window if the series actually reaches back far
                # enough; otherwise it understates the true period return.
                if first_date is not None and first_date > target:
                    ref = None
                else:
                    ref_pt = _close_on_or_before(pts, target) or pts[0]
                    ref = float(ref_pt["c"]) if ref_pt else None

        if ref:
            out[w] = round((last_c - ref) / ref * 100, 2)
    return out
