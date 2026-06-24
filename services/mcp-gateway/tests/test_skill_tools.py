"""The archive-backed Skill catalog, exposed as MCP tools.

Asserts: (1) every skill registers as an @mcp.tool alongside the original three; (2) a skill call
emits the same gap-free tool_call/tool_result trace pair the existing tools do, carrying the
canonical skill name + the archive provenance source; (3) with no archive wired the tools still
register and degrade to an ARCHIVE_UNAVAILABLE warning (never crash).
"""
from __future__ import annotations

import numpy as np
import pytest

from doomberg_core import SKILLS, Core
from doomberg_mcp import InMemoryTrace, Toolset

R = "11111111-1111-1111-1111-111111111111"
AGENT = "agent_x"


class _MiniArchive:
    """Just enough of the ArchiveGateway protocol for the trace/registration tests."""

    def ohlcv(self, symbol, start=None, end=None):
        return [{"symbol": symbol.upper(), "d": "2024-01-01", "o": 1, "h": 1, "l": 1, "c": 1.0,
                 "v": 1e6, "updated_at": "2024-06-01T00:00:00Z"},
                {"symbol": symbol.upper(), "d": "2024-01-02", "o": 1, "h": 1, "l": 1, "c": 1.5,
                 "v": 1e6, "updated_at": "2024-06-01T00:00:00Z"}]

    def ohlcv_panel(self, symbols, start=None, end=None):
        return [], np.zeros((0, 0)), []

    def universe(self, tracked_only=True):
        return [{"symbol": "NVDA", "name": "NVIDIA", "sector": "semiconductors", "tracked": True,
                 "pending": False, "status": "active", "updated_at": "2024-06-01T00:00:00Z"}]

    def sectors(self):
        return [{"id": "semiconductors", "name": "Semiconductors", "updated_at": "2024-06-01T00:00:00Z"}]

    def fundamentals(self, symbols):
        return [{"symbol": "NVDA", "name": "NVIDIA", "price": 150.0, "change_pct": 1.0,
                 "market_cap": 3e12, "pe_ratio": 60.0, "volume": 1e7, "revenue": 6e10,
                 "net_margin": 50.0, "eps": 2.0, "dividend_yield": 0.0, "beta": 1.5,
                 "week52_high": 160.0, "week52_low": 40.0, "updated_at": "2024-06-01T00:00:00Z"}
                for s in symbols if s.upper() == "NVDA"]

    def fundamentals_pit(self, symbol, as_of):
        if symbol.upper() != "NVDA":
            return None
        return {"symbol": "NVDA", "period_end": "2024-01-31", "report_date": "2024-02-21",
                "revenue": 2.2e10, "net_income": 1.2e10, "net_margin": 55.0, "eps": 5.0,
                "report_estimated": False, "source": "edgar", "updated_at": "2024-02-21T00:00:00Z"}

    def analyst_ratings(self, symbols):
        return [{"symbol": "NVDA", "name": "NVIDIA", "covered": True, "consensus_key": "buy",
                 "recommendation_mean": 1.5, "num_analysts": 40, "strong_buy": 25, "buy": 12,
                 "hold": 3, "sell": 0, "strong_sell": 0, "target_mean": 180.0, "target_high": 220.0,
                 "target_low": 140.0, "target_median": 175.0, "current_price": 150.0,
                 "changes": [], "updated_at": "2024-06-01T00:00:00Z"}
                for s in symbols if s.upper() == "NVDA"]

    def news(self, ticker=None, sector=None, limit=50):
        return [{"id": "n1", "headline": "h", "source": "Reuters", "summary": "s", "url": "u",
                 "published_at": "2024-05-23T12:00:00Z", "sentiment": "positive",
                 "tickers": ["NVDA"], "sector": "semiconductors", "fetched_at": "2024-05-23T13:00:00Z"}]

    def sentiment(self, scope_type, scope):
        return {"scope_type": scope_type, "scope": scope, "overall": 0.4, "label": "bullish",
                "sources": [], "trend": [], "updated_at": "2024-06-01T00:00:00Z"}

    def congress_trades(self, ticker=None, member=None, limit=100):
        return [{"id": "c1", "member": "Rep A", "chamber": "House", "party": "R", "ticker": "NVDA",
                 "txn_type": "buy", "amount_range": "$1,001 - $15,000", "amount_low": 1001.0,
                 "amount_high": 15000.0, "transaction_date": "2024-04-01",
                 "disclosure_date": "2024-05-01", "source_url": "u", "fetched_at": "2024-05-02T00:00:00Z"}]

    def insider_transactions(self, symbol, limit=100):
        return [{"accession_no": "a1", "txn_seq": 0, "symbol": symbol.upper(), "cik": "C",
                 "issuer_name": "NVIDIA", "insider_name": "X", "role": "CEO", "transaction_code": "S",
                 "transaction_type": "Sale", "is_derivative": False, "shares": 100.0, "price": 150.0,
                 "value": 15000.0, "transaction_date": "2024-05-15", "filing_date": "2024-05-17",
                 "form": "4", "url": "u", "updated_at": "2024-05-17T00:00:00Z"}]

    def inst_holdings(self, ticker=None, cik=None, period=None):
        return [{"cik": "C1", "period": "2024-03-31", "cusip": "X", "put_call": "",
                 "institution": "Vanguard", "ticker": "NVDA", "name": "NVIDIA", "shares": 1000.0,
                 "value": 1.5e5, "url": "u", "updated_at": "2024-05-15T00:00:00Z"}]

    def inst_filings(self, cik=None, period=None):
        return [{"cik": "C1", "period": "2024-03-31", "institution": "Vanguard",
                 "form": "13F-HR", "filing_date": "2024-05-15", "total_value": 5e11,
                 "url": "u", "updated_at": "2024-05-15T00:00:00Z"}]

    def etf_holdings(self, etf):
        return [{"etf": etf.upper(), "symbol": "NVDA", "name": "NVIDIA", "weight": 0.1,
                 "as_of": "2024-05-31", "updated_at": "2024-06-01T00:00:00Z"}]

    def etf_exposure(self, symbol):
        return [{"etf": "SOXX", "symbol": symbol.upper(), "name": "NVIDIA", "weight": 0.1,
                 "as_of": "2024-05-31", "updated_at": "2024-06-01T00:00:00Z"}]

    def macro(self):
        return {"prices": [{"symbol": "SPX", "name": "S&P", "price": 5300.0, "change_pct": 0.5,
                            "updated_at": "2024-06-01T00:00:00Z"}],
                "quotes": []}


@pytest.fixture
def archive_toolset() -> Toolset:
    return Toolset(core=Core(), sink=InMemoryTrace(), archive=_MiniArchive())


def test_call_skill_traces_like_ohlcv(archive_toolset):
    out = archive_toolset.call_skill("market.news", {"ticker": "NVDA"},
                                     _ctx={"run_id": R, "agent_id": AGENT})
    assert out["provenance"]["source"] == "doomberg-v1-archive"
    events = archive_toolset.sink.events(R)
    assert [e["type"] for e in events] == ["tool_call", "tool_result"]
    assert [e["seq"] for e in events] == [0, 1]  # gap-free
    assert events[0]["data"]["name"] == "market.news"  # canonical tool name the read-model pairs on


def test_computed_skill_traces_with_computed_source(archive_toolset):
    # A pure-math (agent-input) computed skill needs no archive and is sourced "computed".
    out = archive_toolset.call_skill(
        "options.greeks", {"S": 100, "K": 100, "T": 1.0, "r": 0.05, "sigma": 0.2, "type": "call"},
        _ctx={"run_id": R, "agent_id": AGENT})
    assert out["provenance"]["source"] == "computed"
    assert out["provenance"]["inputs"] == "agent"
    assert out["data"]["price"] > 0
    events = archive_toolset.sink.events(R)
    assert [e["type"] for e in events] == ["tool_call", "tool_result"]
    assert events[0]["data"]["name"] == "options.greeks"
    assert events[1]["data"]["summary"]["source"] == "computed"


def test_pit_skill_marks_pit_true_in_summary(archive_toolset):
    out = archive_toolset.call_skill("fundamentals.pit", {"symbol": "NVDA", "as_of": "2024-05-01"},
                                     _ctx={"run_id": R})
    assert out["provenance"]["pit"] == "true"
    result = archive_toolset.sink.events(R)[-1]
    assert result["data"]["summary"]["pit"] == "true"


def test_unknown_skill_raises(archive_toolset):
    with pytest.raises(ValueError):
        archive_toolset.call_skill("not.a.skill", {})


async def test_server_advertises_all_skill_tools(archive_toolset):
    from doomberg_mcp import create_server

    mcp, _ = create_server(archive_toolset)
    names = {t.name for t in await mcp.list_tools()}
    # the original three
    assert {"market_get_ohlcv", "backtest_run", "propose_strategy"} <= names
    # every skill (the registry name with dots → underscores is the @mcp.tool name)
    expected = {tool.replace(".", "_") for tool in SKILLS}
    assert expected <= names
    assert len(names) >= 3 + len(SKILLS)


def test_skills_degrade_without_archive():
    ts = Toolset(core=Core(), sink=InMemoryTrace())  # archive=None
    out = ts.call_skill("fundamentals.get", {"symbol": "NVDA"}, _ctx={"run_id": R})
    assert out["data"] is None
    assert out["warnings"][0]["code"] == "ARCHIVE_UNAVAILABLE"
    # still traced
    assert [e["type"] for e in ts.sink.events(R)] == ["tool_call", "tool_result"]
