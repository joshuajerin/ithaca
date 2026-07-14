"""Aggregate wall-clock deadline for a worker job.

The v1 post-mortem lesson: a *per-call* timeout is not enough — a job that makes
many fast-but-not-instant calls can blow its total budget while every individual
call stays under its own limit. So we track ONE aggregate wall-clock deadline for
the whole job and derive every per-call timeout from the time *remaining*:

    per_call_timeout = min(default_per_call, remaining)

``Deadline`` is monotonic-clock based (``time.monotonic``) so it is immune to wall
clock adjustments. It is cheap, dependency-free, and trivially testable: inject a
``clock`` callable in tests to simulate elapsed time deterministically.
"""

from __future__ import annotations

import time
from typing import Callable

__all__ = ["Deadline", "DeadlineExceeded"]


class DeadlineExceeded(TimeoutError):
    """The aggregate wall-clock budget for a job has been exhausted."""


class Deadline:
    """An aggregate wall-clock budget measured against a monotonic clock.

    Create one at the entry of a job::

        dl = Deadline.from_ms(30_000)
        ...
        dl.check("before backtest")          # raises DeadlineExceeded if blown
        t = dl.per_call_ms(default_ms=5_000) # min(default, remaining)
    """

    __slots__ = ("_budget_s", "_start", "_clock")

    def __init__(self, budget_s: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        if budget_s <= 0:
            raise ValueError(f"deadline budget must be positive, got {budget_s}")
        self._budget_s = float(budget_s)
        self._clock = clock
        self._start = clock()

    @classmethod
    def from_ms(cls, budget_ms: int, *, clock: Callable[[], float] = time.monotonic) -> "Deadline":
        return cls(budget_ms / 1000.0, clock=clock)

    def elapsed_s(self) -> float:
        return self._clock() - self._start

    def remaining_s(self) -> float:
        """Seconds left in the budget; clamped at 0 (never negative)."""
        return max(0.0, self._budget_s - self.elapsed_s())

    def remaining_ms(self) -> int:
        return int(self.remaining_s() * 1000.0)

    def expired(self) -> bool:
        return self.remaining_s() <= 0.0

    def check(self, where: str = "") -> None:
        """Raise :class:`DeadlineExceeded` if the aggregate budget is exhausted."""
        if self.expired():
            suffix = f" at {where}" if where else ""
            raise DeadlineExceeded(
                f"aggregate wall-clock deadline exceeded{suffix} "
                f"(budget={self._budget_s:.3f}s, elapsed={self.elapsed_s():.3f}s)"
            )

    def per_call_ms(self, default_ms: int) -> int:
        """Per-call timeout = min(default, remaining). Always >= 0."""
        return max(0, min(int(default_ms), self.remaining_ms()))
