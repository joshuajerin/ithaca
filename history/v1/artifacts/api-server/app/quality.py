"""Data-quality validation for OHLCV series.

Runs a real validation pass over a fetched series and reports issues without
ever altering or synthesizing the data: gaps (missing expected periods), stale
freshness, NaN / missing OHLC rows, zero-volume bars and duplicate timestamps.
The caller decides how to present the findings; this module only measures.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional

# Minutes per intraday interval, for gap detection on intraday series.
_INTERVAL_MIN = {
    "1m": 1, "2m": 2, "5m": 5, "15m": 15, "30m": 30,
    "60m": 60, "90m": 90, "1h": 60,
}

# Default "stale" thresholds (seconds). Daily series tolerate a long weekend +
# holiday before they count as stale; intraday tolerates a couple of days so a
# series captured before a weekend isn't falsely flagged.
_STALE_DAILY = 4 * 86400
_STALE_INTRADAY = 2 * 86400


def _parse_dt(t) -> Optional[datetime]:
    if not isinstance(t, str):
        return None
    try:
        if "T" in t:
            return datetime.fromisoformat(t.replace("Z", "+00:00"))
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _is_nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _business_days_between(d0, d1) -> int:
    """Weekday count strictly between two dates (holidays are not modeled)."""
    if (d1 - d0).days <= 0:
        return 0
    cnt = 0
    cur = d0
    while cur < d1:
        cur += timedelta(days=1)
        if cur < d1 and cur.weekday() < 5:
            cnt += 1
    return cnt


def _detect_gaps(parsed: List[datetime], interval: str) -> int:
    if len(parsed) < 2:
        return 0
    gaps = 0
    if interval == "1d":
        for a, b in zip(parsed, parsed[1:]):
            gaps += _business_days_between(a.date(), b.date())
        return gaps
    step = _INTERVAL_MIN.get(interval)
    if not step:
        return 0
    for a, b in zip(parsed, parsed[1:]):
        if a.date() != b.date():
            continue  # overnight / weekend gaps are expected, not missing bars
        delta_min = (b - a).total_seconds() / 60.0
        missing = round(delta_min / step) - 1
        if missing > 0:
            gaps += missing
    return gaps


def validate_series(
    points: List[dict],
    interval: str = "1d",
    as_of: Optional[str] = None,
    stale_after_secs: Optional[float] = None,
) -> dict:
    """Measure quality of an OHLCV series.

    `points` rows use `t` (or `d`) for the timestamp and o/h/l/c/v for values.
    Returns counts plus a human-readable `issues` list. Never mutates `points`.
    """
    rows = len(points)
    seen = set()
    duplicates = 0
    nan_rows = 0
    zero_volume = 0
    dropped = 0  # rows that cleaning would discard (duplicate ts or missing OHLC)
    parsed: List[datetime] = []

    for p in points:
        t = p.get("t") or p.get("d")
        is_dup = False
        if t in seen:
            duplicates += 1
            is_dup = True
        elif t is not None:
            seen.add(t)
        is_nan = any(_is_nan(p.get(k)) for k in ("o", "h", "l", "c"))
        if is_nan:
            nan_rows += 1
        if is_dup or is_nan:
            dropped += 1
        v = p.get("v")
        if _is_nan(v) or v == 0:
            zero_volume += 1
        dt = _parse_dt(t)
        if dt:
            parsed.append(dt)

    parsed.sort()
    gaps = _detect_gaps(parsed, interval)

    # Freshness: prefer an explicit as-of, else the last observed timestamp.
    ref = _parse_dt(as_of) if as_of else (parsed[-1] if parsed else None)
    stale = False
    stale_secs: Optional[int] = None
    if ref is not None:
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        secs = (datetime.now(timezone.utc) - ref).total_seconds()
        stale_secs = int(secs)
        threshold = stale_after_secs if stale_after_secs is not None else (
            _STALE_DAILY if interval == "1d" else _STALE_INTRADAY
        )
        stale = secs > threshold

    issues: List[str] = []
    if gaps:
        issues.append(f"{gaps} missing period(s)")
    if duplicates:
        issues.append(f"{duplicates} duplicate timestamp(s)")
    if nan_rows:
        issues.append(f"{nan_rows} row(s) with missing OHLC")
    if zero_volume:
        issues.append(f"{zero_volume} zero-volume bar(s)")
    if stale:
        issues.append("series is stale")

    if dropped:
        issues.append(f"{dropped} row(s) would be dropped")

    return {
        "rows": rows,
        "gaps": gaps,
        "duplicates": duplicates,
        "nanRows": nan_rows,
        "zeroVolume": zero_volume,
        "droppedRows": dropped,
        "firstDate": parsed[0].isoformat() if parsed else None,
        "lastDate": parsed[-1].isoformat() if parsed else None,
        "stale": stale,
        "staleSeconds": stale_secs,
        "issues": issues,
    }
