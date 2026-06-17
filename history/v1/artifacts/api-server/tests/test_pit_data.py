"""Unit tests for point-in-time (PIT) & survivorship-bias-free data plumbing.

Runnable two ways:
    python artifacts/api-server/tests/test_pit_data.py   # standalone
    pytest artifacts/api-server/tests/test_pit_data.py    # if pytest installed

These tests pin the honesty contract of Task #284:
  * `historical_universe` resolves the universe *active during* a window and
    merges in later-delisted names (curated fallback when the DB is empty), and
    flags `survivorshipSafe` only when delisted names were actually carried.
  * `historical_closes` is real-only: names without genuine OHLCV are reported
    under `missing`, never imputed with a deterministic mock series.
  * `fundamentals_as_of` returns as-reported figures knowable at the as-of date,
    or `None` (the caller must flag the fallback, not silently restate).
  * `pit_coverage` reports PIT-safe vs best-effort-current coverage honestly.
  * `listing_info` returns an honest status from DB → curated → unknown.
None of these tests touch a real database.
"""
from __future__ import annotations

import contextlib
import os
import sys
from datetime import date

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import data, db, repo  # noqa: E402


# ----------------------------------------------------------------------------
# DB stubbing helpers
# ----------------------------------------------------------------------------
def _boom(*_a, **_k):
    raise RuntimeError("db down")


@contextlib.contextmanager
def fake_db(available=True, query=None, query_one=None):
    orig = {k: getattr(db, k) for k in ("db_available", "query", "query_one", "execute", "execute_many")}
    db.db_available = lambda: available
    db.query = query or _boom
    db.query_one = query_one or _boom
    db.execute = lambda *a, **k: None
    db.execute_many = lambda *a, **k: None
    try:
        yield
    finally:
        for k, v in orig.items():
            setattr(db, k, v)


# ----------------------------------------------------------------------------
# Tiny assertion harness (works with or without pytest)
# ----------------------------------------------------------------------------
_PASSED = 0
_FAILED = 0


def check(cond, msg):
    global _PASSED, _FAILED
    if cond:
        _PASSED += 1
    else:
        _FAILED += 1
        print(f"  FAIL: {msg}")


# ----------------------------------------------------------------------------
# historical_universe
# ----------------------------------------------------------------------------
def test_historical_universe_curated_fallback_includes_delisted():
    """DB down → curated DELISTED names trading in the window are merged in and
    survivorshipSafe is honest."""
    with fake_db(available=False):
        # GFC window: Lehman/Bear/WaMu/Enron... several delisted names overlap.
        u = repo.historical_universe("2008-01-01", "2008-12-31")
    check(u["source"] == "mock", "curated fallback source should be 'mock'")
    syms = {d["symbol"] for d in u["delisted"]}
    check("LEHMQ" in syms, "Lehman should be in 2008 window")
    check("BSC" in syms, "Bear Stearns should be in 2008 window")
    # Enron delisted 2002 — NOT in a 2008 window.
    check("ENRNQ" not in syms, "Enron (delisted 2002) must not appear in 2008 window")
    check(u["survivorshipSafe"] is True, "window with delisted names is survivorship-safe")
    check(u["delistedCount"] == len(u["delisted"]), "delistedCount matches list length")
    check(all(s in u["symbols"] for s in syms), "delisted symbols merged into combined list")


def test_historical_universe_recent_window_no_delisted_is_flagged():
    """A window with no curated delistings is honestly flagged as survivor-only."""
    with fake_db(available=False):
        u = repo.historical_universe("2025-01-01", "2025-06-01")
    check(u["delistedCount"] == 0, "no curated delistings in 2025 window")
    check(u["survivorshipSafe"] is False, "no delisted names → not survivorship-safe")
    check(any("survivorship" in n.lower() for n in u["notes"]), "must carry an honest survivorship note")


def test_historical_universe_sector_filter():
    """Sector filter narrows curated delisted names (financials in GFC)."""
    with fake_db(available=False):
        u = repo.historical_universe("2008-01-01", "2008-12-31", sector="financials")
    sectors = {d["sector"] for d in u["delisted"]}
    check(sectors <= {"financials"}, f"sector filter should keep only financials, got {sectors}")
    check(any(d["symbol"] == "LEHMQ" for d in u["delisted"]), "Lehman (financials) kept under filter")


# ----------------------------------------------------------------------------
# historical_closes — real-only, no mock fill
# ----------------------------------------------------------------------------
def test_historical_closes_reports_missing_not_mock():
    """Names without real OHLCV are reported as missing, never imputed."""
    captured = {}

    def q(sql, params):
        captured["sql"] = sql
        # Only AAA has real rows; BBB has none.
        return [
            {"symbol": "AAA", "d": date(2020, 1, 2), "c": 10.0, "updated_at": None},
            {"symbol": "AAA", "d": date(2020, 1, 3), "c": 11.0, "updated_at": None},
        ]

    with fake_db(available=True, query=q):
        res = repo.historical_closes(["AAA", "BBB"], "2020-01-01", "2020-12-31")
    check(res["covered"] == ["AAA"], "only AAA has real coverage")
    check(res["missing"] == ["BBB"], "BBB reported missing, not imputed")
    check("AAA" in res["series"] and len(res["series"]["AAA"]) == 2, "AAA real series returned")
    check(res["source"] == "live", "covered series → source live")


def test_historical_closes_drops_single_point_series():
    """A name with <2 points is treated as not covered (can't form a return)."""
    def q(sql, params):
        return [{"symbol": "AAA", "d": date(2020, 1, 2), "c": 10.0, "updated_at": None}]

    with fake_db(available=True, query=q):
        res = repo.historical_closes(["AAA"], "2020-01-01", "2020-12-31")
    check(res["covered"] == [], "single-point series is not covered")
    check(res["missing"] == ["AAA"], "single-point name reported missing")
    check(res["source"] == "none", "no covered series → source none")


def test_historical_closes_no_db_is_empty_not_mock():
    with fake_db(available=False):
        res = repo.historical_closes(["AAA", "BBB"], "2020-01-01", "2020-12-31")
    check(res["series"] == {}, "no DB → no series (never mock)")
    check(set(res["missing"]) == {"AAA", "BBB"}, "all names missing when DB down")


# ----------------------------------------------------------------------------
# fundamentals_as_of — as-reported or None
# ----------------------------------------------------------------------------
def test_fundamentals_as_of_returns_as_reported():
    def q(sql, params):
        # latest first; trailing four quarters for TTM
        return [
            {"period_end": date(2021, 9, 30), "report_date": date(2021, 10, 28), "revenue": 100.0,
             "net_income": 20.0, "net_margin": 0.20, "eps": 1.0, "report_estimated": False, "source": "pit"},
            {"period_end": date(2021, 6, 30), "report_date": date(2021, 7, 28), "revenue": 90.0,
             "net_income": 18.0, "net_margin": 0.20, "eps": 0.9, "report_estimated": False, "source": "pit"},
            {"period_end": date(2021, 3, 31), "report_date": date(2021, 4, 28), "revenue": 80.0,
             "net_income": 16.0, "net_margin": 0.20, "eps": 0.8, "report_estimated": False, "source": "pit"},
            {"period_end": date(2020, 12, 31), "report_date": date(2021, 1, 28), "revenue": 70.0,
             "net_income": 14.0, "net_margin": 0.20, "eps": 0.7, "report_estimated": False, "source": "pit"},
        ]

    with fake_db(available=True, query=q):
        f = repo.fundamentals_as_of("AAA", "2021-12-31")
    check(f is not None, "fundamentals returned when PIT rows exist")
    check(f["periodEnd"] == "2021-09-30", "latest period end picked")
    check(f["reportDate"] == "2021-10-28", "latest report date picked")
    check(abs(f["epsTtm"] - 3.4) < 1e-9, "TTM EPS = sum of 4 quarters")
    check(abs(f["revenueTtm"] - 340.0) < 1e-9, "TTM revenue = sum of 4 quarters")
    check(f["quartersUsed"] == 4, "four quarters used")


def test_fundamentals_as_of_none_when_no_pit():
    def q(sql, params):
        return []

    with fake_db(available=True, query=q):
        f = repo.fundamentals_as_of("AAA", "2021-12-31")
    check(f is None, "no PIT rows → None (caller flags fallback, never restates)")
    with fake_db(available=False):
        check(repo.fundamentals_as_of("AAA", "2021-12-31") is None, "no DB → None")


# ----------------------------------------------------------------------------
# pit_coverage
# ----------------------------------------------------------------------------
def test_pit_coverage_counts_and_range():
    def q(sql, params):
        return [
            {"symbol": "AAA", "n": 8, "pmin": date(2019, 12, 31), "pmax": date(2021, 9, 30), "upd": None},
            # BBB present with zero rows shouldn't happen via GROUP BY, but covered=only AAA
        ]

    with fake_db(available=True, query=q):
        cov = repo.pit_coverage(["AAA", "BBB"])
    check(cov["total"] == 2, "total counts requested symbols")
    check(cov["covered"] == 1, "only AAA covered")
    check(cov["perSymbol"]["AAA"] is True and cov["perSymbol"]["BBB"] is False, "perSymbol honest")
    check(cov["periodRange"]["min"] == "2019-12-31", "period min surfaced")
    check(cov["periodRange"]["max"] == "2021-09-30", "period max surfaced")


def test_pit_coverage_no_db_zero():
    with fake_db(available=False):
        cov = repo.pit_coverage(["AAA", "BBB"])
    check(cov["covered"] == 0, "no DB → zero covered")
    check(cov["total"] == 2, "total still counts requested")


# ----------------------------------------------------------------------------
# listing_info — DB → curated → unknown
# ----------------------------------------------------------------------------
def test_listing_info_curated_delisted():
    with fake_db(available=False):
        li = repo.listing_info("LEHMQ")
    check(li["status"] == "delisted", "curated delisted status")
    check(li["delistedAt"] == "2008-09-17", "curated delisted date")
    check(li["source"] == "curated", "source curated when DB down")


def test_listing_info_unknown():
    with fake_db(available=False):
        li = repo.listing_info("ZZZZ_NOT_A_TICKER")
    check(li["status"] == "unknown", "unknown ticker → unknown status")
    check(li["listedAt"] is None and li["delistedAt"] is None, "no dates for unknown")


def test_listing_info_db_priority():
    def q1(sql, params):
        return {"symbol": "AAA", "name": "Alpha", "sector": "tech",
                "status": "active", "listed_at": date(2010, 1, 4), "delisted_at": None}

    with fake_db(available=True, query_one=q1):
        li = repo.listing_info("AAA")
    check(li["source"] == "db", "DB row takes priority")
    check(li["listedAt"] == "2010-01-04", "DB listed date surfaced (iso)")
    check(li["status"] == "active", "DB status surfaced")


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------
def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        print(f"• {t.__name__}")
        t()
    print(f"\n{_PASSED} passed, {_FAILED} failed")
    return _FAILED == 0


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
