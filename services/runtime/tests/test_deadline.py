"""Tests for the aggregate wall-clock Deadline."""

from __future__ import annotations

import pytest

from ithaca_runtime.deadline import Deadline, DeadlineExceeded


def test_remaining_and_per_call_clamp():
    clock = iter([0.0, 0.0, 2.0, 2.0, 2.0])
    dl = Deadline.from_ms(5_000, clock=lambda: next(clock))
    assert dl.remaining_ms() == 5_000        # t=0
    # remaining = 3s; per-call default 10s clamps to remaining (3000ms)
    assert dl.per_call_ms(10_000) == 3_000
    # per-call default below remaining is preserved
    assert dl.per_call_ms(1_000) == 1_000


def test_check_raises_when_exhausted():
    clock = iter([0.0, 5.0, 5.0])
    dl = Deadline.from_ms(1_000, clock=lambda: next(clock))
    with pytest.raises(DeadlineExceeded):
        dl.check("here")


def test_remaining_never_negative_and_per_call_zero_when_blown():
    clock = iter([0.0, 9.0, 9.0])
    dl = Deadline.from_ms(1_000, clock=lambda: next(clock))
    assert dl.remaining_s() == 0.0
    assert dl.per_call_ms(5_000) == 0


def test_positive_budget_required():
    with pytest.raises(ValueError):
        Deadline(0)
