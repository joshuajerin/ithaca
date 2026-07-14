"""A minimal market calendar gate for the paper scheduler.

HONEST SCOPE: this is a weekday + regular-trading-hours gate for US equities, expressed in
UTC. It does NOT know exchange holidays, half-days, or DST shifts (RTH is pinned to the
13:30–20:00 UTC window that matches 09:30–16:00 ET during EDT). It exists so the scheduler
does not tick a daily strategy on a weekend; a production deployment swaps in a real
exchange-calendar library behind the same :meth:`is_open` seam.

``AlwaysOpen`` is the right choice for a daily-close strategy (it rebalances once per day on
the freshest mark and the staleness gate in ``run_paper_tick`` is the real guard) and for
deterministic tests.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Protocol

__all__ = ["MarketCalendar", "RegularHoursCalendar", "AlwaysOpen"]


class MarketCalendar(Protocol):
    def is_open(self, when: datetime | None = None) -> bool: ...


def _as_utc(when: datetime | None) -> datetime:
    when = when or datetime.now(timezone.utc)
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


class RegularHoursCalendar:
    """Open Mon–Fri within an intraday UTC window (default 13:30–20:00, ~RTH during EDT)."""

    def __init__(self, open_utc: time = time(13, 30), close_utc: time = time(20, 0)) -> None:
        self._open = open_utc
        self._close = close_utc

    def is_open(self, when: datetime | None = None) -> bool:
        w = _as_utc(when)
        if w.weekday() >= 5:  # Saturday/Sunday
            return False
        return self._open <= w.timetz().replace(tzinfo=None) < self._close


class AlwaysOpen:
    """Always open — for daily-close strategies and deterministic tests."""

    def is_open(self, when: datetime | None = None) -> bool:  # noqa: ARG002
        return True
