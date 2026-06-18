"""Network-free Toolset wired to a deterministic synthetic price source."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from doomberg_core import Core, DataGateway
from doomberg_mcp import InMemoryTrace, Toolset


def _trading_days(n: int, start: str = "2024-01-01") -> list[str]:
    y, m, d = (int(x) for x in start.split("-"))
    day = dt.date(y, m, d)
    out: list[str] = []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def _fetch_factory(dates, series):
    def _fetch(symbol, range_="1y", interval="1d"):
        su = symbol.upper()
        if su not in series:
            raise ValueError(f"no data for {su}")
        c = series[su]
        pts = [{"d": dates[i], "o": c[i], "h": c[i], "l": c[i], "c": c[i], "v": 1e6} for i in range(len(dates))]
        return {"points": pts, "quote": {"symbol": su, "price": c[-1], "asOf": dates[-1] + "T20:00:00Z"}}
    return _fetch


@pytest.fixture
def toolset_core() -> Core:
    """A network-free Core wired to a deterministic synthetic price source."""
    dates = _trading_days(250)
    rng = np.random.default_rng(7)
    series = {
        s: list(100 * np.cumprod(1 + rng.normal(d, 0.012, 250)))
        for s, d in {"AAA": 0.0010, "BBB": 0.0003, "CCC": -0.0005}.items()
    }
    return Core(DataGateway(fetch_history=_fetch_factory(dates, series)))


@pytest.fixture
def toolset(toolset_core) -> Toolset:
    return Toolset(core=toolset_core, sink=InMemoryTrace())


@pytest.fixture
def sample_spec() -> dict:
    return {
        "spec_version": "1.0",
        "name": "demo",
        "universe": {"symbols": ["AAA", "BBB", "CCC"], "source": "prices"},
        "strategy": {"id": "momentum", "params": {"lookback": 60}},
        "construction": {"scheme": "rank_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.5},
        "execution": {"cost_bps": 5, "algo": "vwap", "rebalance": "monthly@close"},
        "seed": 42,
    }
