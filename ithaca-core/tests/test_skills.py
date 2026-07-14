"""Skill-catalog tests: each archive-backed skill's shape + provenance envelope + pit flag."""
from __future__ import annotations

import pytest

from ithaca_core import SKILLS, ArchiveGateway, SkillSet
from fake_archive import FakeArchive


@pytest.fixture
def skills() -> SkillSet:
    return SkillSet(FakeArchive())


# ----------------------------- envelope invariants -----------------------------
def _assert_envelope(out: dict, *, pit: bool = False) -> None:
    assert set(out) >= {"data", "provenance", "partial", "warnings"}
    prov = out["provenance"]
    assert prov["source"] == "ithaca-v1-archive"
    assert prov["pit"] == ("true" if pit else "false")
    assert prov["freshness"] == "stale"
    assert "as_of" in prov
    assert "coverage" in prov
    assert "cost" in prov
    assert isinstance(out["warnings"], list)


def test_fake_archive_satisfies_protocol():
    # runtime_checkable structural check — FakeArchive duck-types ArchiveGateway.
    assert isinstance(FakeArchive(), ArchiveGateway)


# The 16 archive-backed skills (source="ithaca-v1-archive"); the rest are COMPUTED.
_ARCHIVE_SKILLS = {
    "market.news", "market.screener", "market.movers", "fundamentals.get", "fundamentals.compare",
    "fundamentals.pit", "analyst.ratings", "congress.trades", "insider.activity",
    "institutional.holdings", "institutional.flows", "etf.holdings", "etf.exposure",
    "sentiment.get", "macro.dashboard", "universe.list",
}


def test_registry_maps_every_skill_to_a_real_method(skills):
    assert len(_ARCHIVE_SKILLS) == 16
    assert _ARCHIVE_SKILLS <= set(SKILLS)
    for tool, method in SKILLS.items():
        assert hasattr(skills, method), f"{tool} -> {method} missing"


def test_every_skill_returns_a_valid_envelope(skills):
    """Smoke: call each ARCHIVE skill with a reasonable arg set and assert the envelope shape.

    COMPUTED skills (source="computed") are covered in test_computed_skills.py."""
    args = {
        "market.news": {"ticker": "NVDA"},
        "market.screener": {},
        "market.movers": {},
        "fundamentals.get": {"symbol": "NVDA"},
        "fundamentals.compare": {"symbols": ["NVDA", "AMD"]},
        "fundamentals.pit": {"symbol": "NVDA", "as_of": "2024-03-01"},
        "analyst.ratings": {"symbol": "NVDA"},
        "congress.trades": {"ticker": "NVDA"},
        "insider.activity": {"symbol": "NVDA"},
        "institutional.holdings": {"symbol": "NVDA"},
        "institutional.flows": {"symbol": "NVDA"},
        "etf.holdings": {"etf": "SOXX"},
        "etf.exposure": {"symbol": "NVDA"},
        "sentiment.get": {"symbol": "NVDA"},
        "macro.dashboard": {},
        "universe.list": {},
    }
    assert set(args) == _ARCHIVE_SKILLS
    for tool in _ARCHIVE_SKILLS:
        out = getattr(skills, SKILLS[tool])(args[tool])
        _assert_envelope(out, pit=(tool == "fundamentals.pit"))


# ----------------------------- per-skill content -----------------------------
def test_market_news_shapes_items_and_sentiment(skills):
    out = skills.market_news({"ticker": "NVDA"})
    _assert_envelope(out)
    items = out["data"]["items"]
    assert items and items[0]["headline"] == "NVDA beats earnings"
    assert out["data"]["sentimentMix"]["positive"] == 1
    assert out["provenance"]["as_of"] == "2024-05-23T13:00:00Z"  # max fetched_at


def test_screener_joins_returns_and_ranks_by_mcap(skills):
    out = skills.market_screener({})
    rows = out["data"]["rows"]
    assert [r["symbol"] for r in rows] == ["NVDA", "TSM", "AMD"]  # by market cap desc
    nvda = next(r for r in rows if r["symbol"] == "NVDA")
    assert nvda["ret1Y"] == pytest.approx(50.0)  # 100 -> 150


def test_movers_has_gainers_and_losers(skills):
    out = skills.market_movers({})
    assert out["data"]["cells"]
    assert "gainers" in out["data"] and "losers" in out["data"]


def test_fundamentals_get_metric_cards(skills):
    out = skills.fundamentals_get({"symbol": "NVDA"})
    labels = {m["label"] for m in out["data"]["metrics"]}
    assert {"Market Cap", "P/E (TTM)", "Revenue (TTM)", "Beta"} <= labels
    assert out["data"]["latestReport"]["eps"] == pytest.approx(5.16)
    assert out["provenance"]["pit"] == "false"  # headline metrics are restated


def test_fundamentals_compare_table(skills):
    out = skills.fundamentals_compare({"symbols": ["NVDA", "AMD"]})
    assert len(out["data"]["companies"]) == 2
    assert out["data"]["metricLabels"][0] == "Price"


def test_fundamentals_compare_reports_missing(skills):
    out = skills.fundamentals_compare({"symbols": ["NVDA", "ZZZZ"]})
    assert out["warnings"][0]["code"] == "PARTIAL_COVERAGE"
    assert out["warnings"][0]["scope"] == "ZZZZ"


def test_fundamentals_pit_is_point_in_time(skills):
    # as_of before the Feb report → only the Nov report is "known".
    out = skills.fundamentals_pit({"symbol": "NVDA", "as_of": "2024-01-01"})
    _assert_envelope(out, pit=True)
    assert out["data"]["report"]["reportDate"] == "2023-11-21"
    assert out["provenance"]["pit"] == "true"


def test_fundamentals_pit_picks_latest_known_report(skills):
    out = skills.fundamentals_pit({"symbol": "NVDA", "as_of": "2024-05-01"})
    assert out["data"]["report"]["reportDate"] == "2024-02-21"  # latest <= as_of


def test_fundamentals_pit_no_report_warns(skills):
    out = skills.fundamentals_pit({"symbol": "NVDA", "as_of": "2000-01-01"})
    assert out["data"]["report"] is None
    assert out["warnings"][0]["code"] == "PARTIAL_COVERAGE"
    assert out["provenance"]["pit"] == "true"  # capability flag stays true even when empty


def test_analyst_ratings_consensus_and_target(skills):
    out = skills.analyst_ratings({"symbol": "NVDA"})
    assert out["data"]["consensus"]["label"] == "Strong Buy"
    assert out["data"]["priceTarget"]["impliedUpsidePct"] == pytest.approx(20.0)  # 150 -> 180


def test_analyst_ratings_uncovered_warns(skills):
    out = skills.analyst_ratings({"symbol": "AMD"})  # no analyst fixture
    assert out["data"]["covered"] is False
    assert out["warnings"][0]["code"] == "PARTIAL_COVERAGE"


def test_congress_trades_cluster_highlight(skills):
    out = skills.congress_trades({"ticker": "NVDA"})
    assert out["data"]["stats"]["buys"] == 2
    kinds = {h["kind"] for h in out["data"]["highlights"]}
    assert "cluster_buy" in kinds  # 2 members bought NVDA
    assert "large_buy" in kinds  # the $500k upper bound clears the threshold


def test_insider_activity_net_selling(skills):
    out = skills.insider_activity({"symbol": "NVDA"})
    s = out["data"]["summary"]
    assert s["buyCount"] == 1 and s["sellCount"] == 1
    assert s["sentiment"] == "net selling"  # $15M sale dwarfs $740k buy
    assert s["uniqueInsiders"] == 2


def test_institutional_holdings_classifies_changes(skills):
    out = skills.institutional_holdings({"symbol": "NVDA"})
    by_inst = {h["institution"]: h for h in out["data"]["holders"]}
    assert by_inst["Vanguard"]["change"] == "added"  # 150k -> 200k QoQ
    assert by_inst["Citadel"]["change"] == "new"  # filed prior quarter but held 0 then
    # BlackRock filed only one quarter → no comparable prior → can't classify QoQ.
    assert by_inst["BlackRock"]["change"] == "unchanged"
    assert out["data"]["summary"]["holderCount"] == 3


def test_institutional_flows_ranks_buyers(skills):
    out = skills.institutional_flows({"symbol": "NVDA"})
    assert out["data"]["summary"]["buyerCount"] >= 2  # Vanguard (added) + Citadel (new)
    insts = {b["institution"] for b in out["data"]["buyers"]}
    assert {"Vanguard", "Citadel"} <= insts


def test_etf_holdings_concentration(skills):
    out = skills.etf_holdings({"etf": "SOXX"})
    assert out["data"]["holdingsCount"] == 2
    assert out["data"]["rows"][0]["symbol"] == "NVDA"  # highest weight first
    assert out["data"]["top5"] == pytest.approx(0.17)


def test_etf_exposure_reverse_lookup(skills):
    out = skills.etf_exposure({"symbol": "NVDA"})
    etfs = {r["etf"] for r in out["data"]["rows"]}
    assert {"SOXX", "QQQ"} <= etfs  # NVDA is in both fixtures


def test_sentiment_get_snapshot(skills):
    out = skills.sentiment_get({"symbol": "NVDA"})
    assert out["data"]["label"] == "bullish"
    assert out["data"]["overall"] == pytest.approx(0.42)


def test_macro_dashboard_regime(skills):
    out = skills.macro_dashboard({})
    assert out["data"]["count"] == 3
    assert out["data"]["regime"] is not None  # equities up + yields easing -> a regime call


def test_universe_list_summary_and_sectors(skills):
    out = skills.universe_list({})
    # tracked_only default → the delisted/untracked OLD row is excluded
    assert out["data"]["summary"]["totalSymbols"] == 3
    assert any(s["id"] == "semiconductors" for s in out["data"]["sectors"])


def test_universe_list_includes_untracked_when_asked(skills):
    out = skills.universe_list({"tracked_only": False})
    assert out["data"]["summary"]["totalSymbols"] == 4
    assert out["data"]["summary"]["delistedCount"] == 1


# ----------------------------- archive-absent degradation -----------------------------
def test_skillset_without_archive_warns_not_crashes():
    skills = SkillSet(None)
    for tool in _ARCHIVE_SKILLS:
        out = getattr(skills, SKILLS[tool])({"symbol": "NVDA", "etf": "SOXX", "scope": "NVDA",
                                             "symbols": ["NVDA", "AMD"]})
        assert out["data"] is None
        assert out["warnings"][0]["code"] == "ARCHIVE_UNAVAILABLE"
        assert out["provenance"]["source"] == "ithaca-v1-archive"
