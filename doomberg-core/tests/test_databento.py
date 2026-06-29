"""Tests for the Databento data source adapter and DataGateway source selection."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from doomberg_core.sources.databento import (
    DatabentoError,
    DatabentoNoDataError,
    _normalize_symbol,
    _resolve_dataset,
    _range_to_dates,
    fetch_price_history,
    fetch_daily_closes,
)


class TestNormalizeSymbol:
    def test_bare_symbol(self):
        assert _normalize_symbol("AAPL") == "AAPL"

    def test_exchange_prefix_colon(self):
        assert _normalize_symbol("NASDAQ:AAPL") == "AAPL"

    def test_exchange_prefix_slash(self):
        assert _normalize_symbol("XNAS/AAPL") == "AAPL"

    def test_lowercase(self):
        assert _normalize_symbol("aapl") == "AAPL"


class TestResolveDataset:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("DATABENTO_DATASET", raising=False)
        assert _resolve_dataset("AAPL") == "XNAS.ITCH"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DATABENTO_DATASET", "CME.MDP3")
        assert _resolve_dataset("ES") == "CME.MDP3"

    def test_prefix_match(self, monkeypatch):
        monkeypatch.delenv("DATABENTO_DATASET", raising=False)
        assert _resolve_dataset("CME:ESH5") == "CME.MDP3"
        assert _resolve_dataset("NYSE:IBM") == "XNYS.ITCH"


class TestRangeToDates:
    def test_6mo(self):
        start, end = _range_to_dates("6mo")
        delta = end - start
        assert 179 <= delta.days <= 181

    def test_1y(self):
        start, end = _range_to_dates("1y")
        delta = end - start
        assert 364 <= delta.days <= 366

    def test_unknown_defaults_to_180d(self):
        start, end = _range_to_dates("unknown")
        delta = end - start
        assert 179 <= delta.days <= 181


class TestFetchPriceHistory:
    """Tests that mock the Databento client to avoid network calls."""

    def _make_mock_df(self, rows):
        """Build a fake DataFrame-like object."""
        import pandas as pd
        return pd.DataFrame(rows, columns=["ts_event", "open", "high", "low", "close", "volume"])

    def test_no_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
        with pytest.raises(DatabentoError, match="DATABENTO_API_KEY"):
            fetch_price_history("AAPL")

    @patch("doomberg_core.sources.databento._get_client")
    def test_successful_fetch_daily(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("DATABENTO_API_KEY", "test-key")

        # Build mock response
        ts1 = datetime(2024, 1, 15, 21, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 16, 21, 0, 0, tzinfo=timezone.utc)
        df = self._make_mock_df([
            {"ts_event": ts1, "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0, "volume": 1000000},
            {"ts_event": ts2, "open": 151.0, "high": 153.0, "low": 150.5, "close": 152.5, "volume": 1100000},
        ])

        mock_client = MagicMock()
        mock_data = MagicMock()
        mock_data.to_df.return_value = df
        mock_client.timeseries.get_range.return_value = mock_data
        mock_client_cls.return_value = mock_client

        result = fetch_price_history("AAPL", range_="6mo", interval="1d")

        assert "points" in result
        assert len(result["points"]) == 2
        assert result["points"][0]["d"] == "2024-01-15"
        assert result["points"][0]["o"] == 150.0
        assert result["points"][0]["c"] == 151.0
        assert result["points"][0]["v"] == 1000000.0
        assert result["quote"]["symbol"] == "AAPL"
        assert result["quote"]["price"] == 152.5
        assert result["quote"]["changePct"] is not None

    @patch("doomberg_core.sources.databento._get_client")
    def test_empty_data_raises(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("DATABENTO_API_KEY", "test-key")

        import pandas as pd
        mock_client = MagicMock()
        mock_data = MagicMock()
        mock_data.to_df.return_value = pd.DataFrame()
        mock_client.timeseries.get_range.return_value = mock_data
        mock_client_cls.return_value = mock_client

        with pytest.raises(DatabentoNoDataError):
            fetch_price_history("FAKE", range_="1mo")


class TestFetchDailyCloses:
    @patch("doomberg_core.sources.databento._get_client")
    def test_returns_date_to_close_map(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("DATABENTO_API_KEY", "test-key")

        import pandas as pd
        ts1 = datetime(2024, 1, 15, 21, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 16, 21, 0, 0, tzinfo=timezone.utc)
        df = pd.DataFrame([
            {"ts_event": ts1, "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0, "volume": 1000000},
            {"ts_event": ts2, "open": 151.0, "high": 153.0, "low": 150.5, "close": 152.5, "volume": 1100000},
        ])

        mock_client = MagicMock()
        mock_data = MagicMock()
        mock_data.to_df.return_value = df
        mock_client.timeseries.get_range.return_value = mock_data
        mock_client_cls.return_value = mock_client

        result = fetch_daily_closes("AAPL", "2024-01-15", "2024-01-16")

        assert isinstance(result, dict)
        assert result["2024-01-15"] == 151.0
        assert result["2024-01-16"] == 152.5


class TestDataGatewaySourceSelection:
    """Test that DataGateway picks the right source based on env config."""

    def test_defaults_to_yahoo_without_key(self, monkeypatch):
        monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
        monkeypatch.delenv("DOOMBERG_DATA_SOURCE", raising=False)
        from doomberg_core.gateway.data_gateway import DataGateway
        gw = DataGateway()
        assert gw._source == "yahoo-chart"
        assert gw._pit == "false"

    def test_auto_uses_databento_when_key_present(self, monkeypatch):
        monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
        monkeypatch.setenv("DOOMBERG_DATA_SOURCE", "auto")
        from doomberg_core.gateway.data_gateway import DataGateway
        gw = DataGateway()
        assert gw._source == "databento"
        assert gw._pit == "true"

    def test_forced_yahoo_even_with_key(self, monkeypatch):
        monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
        monkeypatch.setenv("DOOMBERG_DATA_SOURCE", "yahoo")
        from doomberg_core.gateway.data_gateway import DataGateway
        gw = DataGateway()
        assert gw._source == "yahoo-chart"
        assert gw._pit == "false"

    def test_forced_databento_without_key_raises_on_fetch(self, monkeypatch):
        monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
        monkeypatch.setenv("DOOMBERG_DATA_SOURCE", "databento")
        from doomberg_core.gateway.data_gateway import DataGateway
        gw = DataGateway()
        assert gw._source == "databento"
        # Fetching will raise DatabentoError when no API key, but the gateway
        # catches it and returns an error envelope
        result = gw.get_ohlcv("AAPL")
        assert result["partial"] is True
        assert result["provenance"]["source"] == "databento"

    def test_explicit_fetch_history_overrides_source(self):
        from doomberg_core.gateway.data_gateway import DataGateway
        custom = lambda s, r, i: {"points": [], "quote": {}}
        gw = DataGateway(fetch_history=custom)
        assert gw._fetch is custom
