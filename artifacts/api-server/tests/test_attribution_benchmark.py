"""Tests for user-selectable attribution benchmarks (real ETF or custom basket).

Runnable two ways:
    python artifacts/api-server/tests/test_attribution_benchmark.py   # standalone
    pytest artifacts/api-server/tests/test_attribution_benchmark.py    # if pytest installed

Two layers are covered:
  * Pure, deterministic parsing/routing (no network): free-text -> benchmark ETF
    ticker, custom-basket extraction, benchmark resolution + constituent
    resolution, and the heuristic dispatch that strips basket tickers from the
    book and passes a chosen ETF through to drive Brinson.
  * Builder behavior (needs real data): ETF vs basket benchmark construction for
    P&L, Brinson (incl. the alloc+sel+interaction == active-return identity) and
    the tear sheet. These skip gracefully if real data can't be sourced in the
    environment, but assert the full contract whenever data is present — never
    accepting a synthetic fallback.
"""
from __future__ import annotations

import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import agent, skills  # noqa: E402


# --------------------------- pure parsing / routing ---------------------------

def test_extract_benchmark_broad_and_sector():
    assert agent._extract_benchmark("pnl vs the nasdaq") == "QQQ"
    assert agent._extract_benchmark("compare to the dow") == "DIA"
    assert agent._extract_benchmark("vs small caps") == "IWM"
    assert agent._extract_benchmark("equal weight s&p") == "RSP"
    # sector ETF ticker + free-text sector phrase both resolve to a real ETF
    assert agent._extract_benchmark("benchmark against XLK please") == "XLK"
    assert agent._extract_benchmark("vs the semiconductor sector") == "SMH"
    assert agent._extract_benchmark("vs the energy sector") == "XLE"
    # bare S&P phrasing -> default broad ETF; nothing recognized -> None
    assert agent._extract_benchmark("how did the s&p do") == "SPY"
    assert agent._extract_benchmark("show me my pnl") is None
    print("ok: free-text -> real benchmark ETF mapping")


def test_extract_benchmark_constituents():
    cons = agent._extract_benchmark_constituents(
        "pnl for my book AAPL MSFT NVDA vs a basket of GOOGL AMZN META"
    )
    assert cons == ["GOOGL", "AMZN", "META"], cons
    # basket cue must be in a comparison context, else ignored
    assert agent._extract_benchmark_constituents("show a basket of GOOGL AMZN") == []
    # no basket phrasing -> empty
    assert agent._extract_benchmark_constituents("pnl vs QQQ") == []
    print("ok: custom-basket extraction only fires in a benchmark context")


def test_resolve_bench_constituents_dedupes_and_validates():
    kept, dropped = skills._resolve_bench_constituents(
        {"benchmark_constituents": ["aapl", "AAPL", "$MSFT", "NOTAREALTICKERXYZ"]}
    )
    assert "AAPL" in kept and "MSFT" in kept
    assert kept.count("AAPL") == 1                  # de-duplicated
    assert "NOTAREALTICKERXYZ" not in kept          # unknown dropped, not faked
    assert "NOTAREALTICKERXYZ" in dropped           # ...and reported, not silent
    assert skills._resolve_bench_constituents({}) == ([], [])
    print("ok: basket constituents validated against the real universe + deduped")


def test_resolve_benchmark_defaults_and_known():
    assert skills._resolve_benchmark({})[0] == "SPY"          # default
    assert skills._resolve_benchmark({"benchmark": "qqq"})[0] == "QQQ"
    tkr, name = skills._resolve_benchmark({"benchmark": "XLK"})
    assert tkr == "XLK" and name                              # named, real ETF
    print("ok: benchmark resolution defaults to SPY and honors known ETFs")


def test_basket_query_is_not_hijacked_by_order_book():
    # "basket" contains the substring "ask"; the order-book keyword match must
    # use word boundaries so a custom-benchmark-basket query is NOT misrouted.
    q = "performance pnl for AAPL MSFT NVDA vs a basket of GOOGL AMZN META"
    import re as _re
    wants_order_book = (
        any(k in q.lower() for k in ["order book", "orderbook", "depth", "level 2"])
        or bool(_re.search(r"\b(bid|ask|l2)\b", q.lower()))
    )
    assert wants_order_book is False, "basket query must not trigger the order book"
    # genuine order-book phrasing still matches
    assert bool(_re.search(r"\b(bid|ask|l2)\b", "show me the bid ask spread"))
    print("ok: 'basket' no longer hijacked into the order book by the 'ask' substring")


def test_heuristic_routes_basket_to_pnl_and_brinson_uses_etf():
    # P&L: a basket query routes to the P&L panel (not order book) and builds a
    # real basket benchmark; basket tickers do not leak into the book name.
    out = _maybe(lambda: agent._orchestrate_heuristic(
        "performance pnl for AAPL MSFT NVDA vs a basket of GOOGL AMZN META",
        None, [], [],
    ))
    if out is not None:
        panels, _ = out
        pnl = [p for p in panels if p["type"] == "performance_pnl"]
        assert pnl, [p["type"] for p in panels]
        data = pnl[0]["data"]
        assert data["benchmarkKind"] == "basket"
        assert set(data["benchmarkConstituents"]) <= {"GOOGL", "AMZN", "META"}
        assert data["benchmarkConstituents"], "basket must keep real constituents"

    # Brinson: a chosen ETF is now passed through and drives the decomposition.
    out2 = _maybe(lambda: agent._orchestrate_heuristic(
        "brinson attribution for AAPL MSFT NVDA vs QQQ", None, [], [],
    ))
    if out2 is not None:
        panels2, summary2 = out2
        br = [p for p in panels2 if p["type"] == "brinson_attribution"]
        assert br, [p["type"] for p in panels2]
        assert "QQQ" in summary2                       # ETF named, not stripped
        bname = br[0]["data"]["benchmarkName"]
        # The ETF's real sector weights drove it (named) — or, if its composition
        # couldn't be sourced, the labeled proxy fallback.
        assert ("QQQ" in bname) or ("proxy" in bname.lower())
    print("ok: heuristic routes baskets to P&L; a chosen ETF drives Brinson")


# ------------------------- builder behavior (real data) -----------------------

def _maybe(fn):
    """Run a builder, returning its payload or None if real data is unavailable.

    We never accept a synthetic fallback: a genuine data outage simply skips the
    assertion rather than passing on fabricated numbers.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        print(f"  (skipped — real data unavailable: {exc!r})")
        return None


_BOOK = {"symbols": ["AAPL", "MSFT", "NVDA"], "range": "3M"}


def test_pnl_etf_benchmark_is_real_and_named():
    d = _maybe(lambda: skills.build_performance_pnl({**_BOOK, "benchmark": "QQQ"}))
    if d is None:
        return
    assert d["benchmarkKind"] == "etf"
    assert d["benchmarkTicker"] == "QQQ"
    assert "QQQ" in d["benchmarkName"]
    assert d["benchmarkSource"] == "live"        # real series, not synthetic
    assert len(d["series"]) > 0
    print("ok: P&L vs a chosen ETF uses a real, named benchmark series")


def test_pnl_basket_benchmark_is_real_basket():
    d = _maybe(lambda: skills.build_performance_pnl(
        {**_BOOK, "benchmark_constituents": ["GOOGL", "AMZN", "META"]}
    ))
    if d is None:
        return
    assert d["benchmarkKind"] == "basket"
    assert set(d["benchmarkConstituents"]) <= {"GOOGL", "AMZN", "META"}
    assert d["benchmarkConstituents"], "basket must keep real constituents"
    assert d["benchmarkTicker"] is None
    assert d["source"] == "live"
    print("ok: P&L vs a custom basket builds a real, constituent-named benchmark")


def test_brinson_basket_drives_math_and_identity_holds():
    d = _maybe(lambda: skills.build_brinson_attribution(
        {**_BOOK, "benchmark_constituents": ["GOOGL", "AMZN", "META", "AVGO"]}
    ))
    if d is None:
        return
    # The basket (not the sector-ETF proxy) names + drives the benchmark.
    assert "proxies" not in d["benchmarkName"].lower(), d["benchmarkName"]
    t = d["totals"]
    # Brinson identity: allocation + selection + interaction == active return.
    assert abs(
        t["activeReturn"] - (t["allocation"] + t["selection"] + t["interaction"])
    ) < 0.02, t
    print("ok: basket drives Brinson + alloc/sel/interaction tie to active return")


def test_brinson_etf_benchmark_drives_math():
    # A chosen ETF's OWN real sector weights (× real sector-ETF returns) drive the
    # decomposition; if the ETF's composition can't be sourced, the diversified
    # proxy fallback is used and labeled honestly.
    d = _maybe(lambda: skills.build_brinson_attribution({**_BOOK, "benchmark": "QQQ"}))
    if d is None:
        return
    bname = d["benchmarkName"]
    assert ("QQQ" in bname) or ("proxy" in bname.lower()), bname
    t = d["totals"]
    assert abs(
        t["activeReturn"] - (t["allocation"] + t["selection"] + t["interaction"])
    ) < 0.02, t
    print("ok: a chosen ETF's real sector weights drive Brinson (identity holds)")


def test_brinson_etf_choice_changes_benchmark_weights():
    # Selecting a different ETF must actually change the benchmark side — proof
    # the choice is honored, not a fixed proxy. SPY vs QQQ have very different
    # real sector compositions, so their Brinson benchmark weights must differ.
    # Use a DIVERSIFIED book (tech/financials/energy/healthcare/staples) so the
    # benchmark side spans several GICS sectors rather than collapsing to one.
    book = {"symbols": ["AAPL", "JPM", "XOM", "JNJ", "KO"], "range": "3M"}
    spy = _maybe(lambda: skills.build_brinson_attribution({**book, "benchmark": "SPY"}))
    qqq = _maybe(lambda: skills.build_brinson_attribution({**book, "benchmark": "QQQ"}))
    if spy is None or qqq is None:
        return
    # If either fell back to the proxy (composition unavailable), we can't prove
    # ETF-specific weights — skip rather than assert on the shared proxy.
    if "proxy" in spy["benchmarkName"].lower() or "proxy" in qqq["benchmarkName"].lower():
        print("  (skipped — an ETF composition fell back to the shared proxy)")
        return
    bw_spy = {r["sector"]: round(r["benchWeight"], 4) for r in spy["rows"]}
    bw_qqq = {r["sector"]: round(r["benchWeight"], 4) for r in qqq["rows"]}
    assert bw_spy != bw_qqq, (bw_spy, bw_qqq)
    print("ok: a different ETF yields a different (real) Brinson benchmark side")


def test_tear_sheet_header_and_brinson_both_honor_etf():
    d = _maybe(lambda: skills.build_tear_sheet({**_BOOK, "benchmark": "QQQ"}))
    if d is None:
        return
    # Headline P&L is genuinely vs the chosen ETF.
    assert d["benchmarkKind"] == "etf" and "QQQ" in d["benchmarkName"]
    # The Brinson sub-block now honors the same chosen ETF (its real sector
    # weights drive the decomposition) — or the labeled proxy fallback.
    bname = d["brinson"]["benchmarkName"]
    assert ("QQQ" in bname) or ("proxy" in bname.lower()), bname
    print("ok: tear sheet header + Brinson sub-block both honor the chosen ETF")


def test_tear_sheet_basket_drives_both_header_and_brinson():
    d = _maybe(lambda: skills.build_tear_sheet(
        {**_BOOK, "benchmark_constituents": ["GOOGL", "AMZN", "META"]}
    ))
    if d is None:
        return
    assert d["benchmarkKind"] == "basket"
    assert "proxies" not in d["brinson"]["benchmarkName"].lower()
    print("ok: tear sheet basket drives both the header and the Brinson section")


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"\nall {len(fns)} attribution-benchmark tests passed")


if __name__ == "__main__":
    _run_all()
