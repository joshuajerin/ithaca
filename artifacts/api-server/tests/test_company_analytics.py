"""Unit tests for Company Analytics drill-down enrichment.

Runnable two ways:
    python artifacts/api-server/tests/test_company_analytics.py   # standalone
    pytest artifacts/api-server/tests/test_company_analytics.py    # if pytest installed

Covers the drill-down feature: every price driver must carry a paragraph-grade
`detail` (distinct from its one-line explanation) so the row is expandable, and
every catalyst must carry a sentiment read plus a multi-sentence breakdown.
"""
from __future__ import annotations

import os
import sys

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import skills  # noqa: E402


# --------------------------- driver detail --------------------------------
def test_fallback_drivers_have_paragraph_detail():
    company = skills.repo.get_company("NVDA")
    drivers = skills._company_analytics_fallback("NVDA", company)
    assert drivers, "fallback produced no drivers"
    for d in drivers:
        detail = (d.get("detail") or "").strip()
        explanation = (d.get("explanation") or "").strip()
        assert detail, f"driver {d['title']!r} has no detail"
        assert detail != explanation, f"driver {d['title']!r} detail just echoes explanation"
        # Paragraph-grade: clearly longer than the one-line explanation.
        assert len(detail) > len(explanation), f"driver {d['title']!r} detail not expanded"


def test_compose_driver_detail_backfills_missing():
    company = skills.repo.get_company("NVDA")
    driver = {"title": "Test", "tag": "bullish", "explanation": "Short reason."}
    detail = skills._compose_driver_detail(company, driver)
    assert detail and detail != driver["explanation"]
    assert company["name"] in detail


def test_build_drivers_all_expandable():
    out = skills.build_company_analytics({"symbol": "NVDA"})
    assert out["drivers"], "no drivers returned"
    for d in out["drivers"]:
        detail = (d.get("detail") or "").strip()
        assert detail, f"driver {d['title']!r} missing detail (row would be non-expandable)"
        assert detail != (d.get("explanation") or "").strip()


# --------------------------- catalyst enrichment ---------------------------
def test_catalysts_have_sentiment_and_breakdown():
    out = skills.build_company_analytics({"symbol": "NVDA"})
    assert out["catalysts"], "no catalysts returned"
    for c in out["catalysts"]:
        assert c.get("sentiment") in ("bullish", "bearish", "neutral"), c
        detail = (c.get("detail") or "").strip()
        assert detail, f"catalyst {c['event']!r} missing breakdown"
        # 2-3 sentence breakdown -> at least two sentence-ending periods.
        assert detail.count(".") >= 2, f"catalyst {c['event']!r} breakdown too short"


def test_catalyst_keyword_boundary_no_false_positive():
    # "software" must not match the bearish keyword "soft".
    company = skills.repo.get_company("NVDA")
    cat = {
        "event": "GTC Developer Conference",
        "date": skills.date.today().isoformat(),
        "impact": "High",
        "description": "Next-gen roadmap and software ecosystem announcements expected.",
    }
    enriched = skills._enrich_catalyst("NVDA", company, cat)
    assert enriched["sentiment"] == "neutral", enriched["sentiment"]


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in funcs:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(funcs)} company-analytics tests passed")


if __name__ == "__main__":
    _run_all()
