"""DB-free tests for the panel-alignment logic in PgArchiveGateway.ohlcv_panel.

We bypass Postgres by stubbing the gateway's ``_rows`` method, so we can assert the
intersection / no-lookahead / ordering invariants the backtest kernel relies on without
a database. The same panel shape -- (dates, closes[T,N], symbols) -- is what
``doomberg_core.run_backtest`` consumes.
"""
from __future__ import annotations

import numpy as np

from doomberg_archive.gateway import PgArchiveGateway


def _gw_with_rows(rows):
    gw = PgArchiveGateway("postgresql://unused")
    gw._rows = lambda sql, params=None: rows  # type: ignore[assignment]
    return gw


def test_panel_intersects_common_dates_no_lookahead():
    # AMD has 4 days, NVDA has 3 days; intersection is the 3 shared days, ascending.
    rows = [
        {"symbol": "AMD", "d": "2026-01-01", "c": 10.0},
        {"symbol": "AMD", "d": "2026-01-02", "c": 11.0},
        {"symbol": "AMD", "d": "2026-01-03", "c": 12.0},
        {"symbol": "AMD", "d": "2026-01-04", "c": 13.0},
        {"symbol": "NVDA", "d": "2026-01-02", "c": 100.0},
        {"symbol": "NVDA", "d": "2026-01-03", "c": 101.0},
        {"symbol": "NVDA", "d": "2026-01-04", "c": 102.0},
    ]
    gw = _gw_with_rows(rows)
    dates, closes, symbols = gw.ohlcv_panel(["AMD", "NVDA"])
    assert dates == ["2026-01-02", "2026-01-03", "2026-01-04"]
    assert symbols == ["AMD", "NVDA"]
    assert closes.shape == (3, 2)
    np.testing.assert_array_equal(
        closes, np.array([[11.0, 100.0], [12.0, 101.0], [13.0, 102.0]])
    )
    # ascending dates => no lookahead when the kernel walks forward.
    assert dates == sorted(dates)


def test_panel_preserves_requested_symbol_order():
    rows = [
        {"symbol": "AAA", "d": "2026-01-01", "c": 1.0},
        {"symbol": "BBB", "d": "2026-01-01", "c": 2.0},
    ]
    gw = _gw_with_rows(rows)
    _, closes, symbols = gw.ohlcv_panel(["BBB", "AAA"])
    assert symbols == ["BBB", "AAA"]
    np.testing.assert_array_equal(closes, np.array([[2.0, 1.0]]))


def test_panel_drops_symbol_with_no_overlap():
    rows = [
        {"symbol": "AMD", "d": "2026-01-01", "c": 10.0},
        {"symbol": "AMD", "d": "2026-01-02", "c": 11.0},
        {"symbol": "XYZ", "d": "2026-02-01", "c": 5.0},  # disjoint -> empty intersection
    ]
    gw = _gw_with_rows(rows)
    dates, closes, symbols = gw.ohlcv_panel(["AMD", "XYZ"])
    # no common day across both -> empty panel (never imputed)
    assert dates == []
    assert closes.shape == (0, 0)
    assert symbols == []


def test_panel_single_symbol():
    rows = [
        {"symbol": "AMD", "d": "2026-01-01", "c": 10.0},
        {"symbol": "AMD", "d": "2026-01-02", "c": 11.0},
    ]
    gw = _gw_with_rows(rows)
    dates, closes, symbols = gw.ohlcv_panel(["AMD"])
    assert dates == ["2026-01-01", "2026-01-02"]
    assert symbols == ["AMD"]
    assert closes.shape == (2, 1)


def test_panel_empty_symbols():
    gw = _gw_with_rows([])
    dates, closes, symbols = gw.ohlcv_panel([])
    assert dates == [] and symbols == [] and closes.shape == (0, 0)
