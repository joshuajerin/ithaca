"""Shared test fixtures: a deterministic, network-free price source."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pytest

_TEST_ROOT = Path(__file__).resolve().parent
if str(_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEST_ROOT))


def _trading_days(n: int, start: str = "2024-01-01") -> list[str]:
    y, m, d = (int(x) for x in start.split("-"))
    day = dt.date(y, m, d)
    out: list[str] = []
    while len(out) < n:
        if day.weekday() < 5:  # Mon-Fri
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def make_series(n: int, drift: float, vol: float, seed: int, start_price: float = 100.0) -> list[float]:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, size=n)
    return list(np.maximum(start_price * np.cumprod(1.0 + rets), 1e-6))


def make_fetch(series_by_symbol: dict[str, list[float]], dates: list[str]):
    """Return a fetch_price_history-compatible callable backed by in-memory series."""

    def _fetch(symbol: str, range_: str = "1y", interval: str = "1d") -> dict:
        su = symbol.upper()
        if su not in series_by_symbol:
            raise ValueError(f"no data for {su}")
        closes = series_by_symbol[su]
        points = [
            {"d": dates[i], "o": closes[i], "h": closes[i], "l": closes[i], "c": closes[i], "v": 1_000_000.0}
            for i in range(len(dates))
        ]
        return {"points": points, "quote": {"symbol": su, "price": closes[-1], "asOf": dates[-1] + "T20:00:00Z"}}

    return _fetch


@pytest.fixture
def panel_3x250():
    """3 symbols, 250 bars, distinct trends so cross-sectional ranking is meaningful."""
    dates = _trading_days(250)
    series = {
        "AAA": make_series(250, drift=0.0010, vol=0.012, seed=1),   # strong up
        "BBB": make_series(250, drift=0.0002, vol=0.015, seed=2),   # mild up
        "CCC": make_series(250, drift=-0.0006, vol=0.018, seed=3),  # down
    }
    return dates, series
