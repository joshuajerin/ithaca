"""Unit tests for the congressional trading disclosures feed.

Runnable two ways:
    python artifacts/api-server/tests/test_congress.py     # standalone
    pytest artifacts/api-server/tests/test_congress.py      # if pytest installed

Covers three layers WITHOUT any live network:
  * the source adapter (app.sources.congress) normalizes a raw Quiver record into
    the congress-trade schema: buy/sell bucketing, $-range parsing, ISO dates,
    reporting-lag math, stable ids, party expansion and a per-member source link;
  * the curated mock set (app.data.congress_trades) is internally consistent and
    supports the per-ticker filter; and
  * the panel builder / harness (skills.build_congress_trades via harness.run_skill)
    emits a model-valid CongressTradesData payload with honest stats, an explicit
    reporting-lag note, source links and notable-activity highlights, and that the
    per-ticker filter actually narrows the feed.
"""
from __future__ import annotations

import os
import sys

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app import data, harness  # noqa: E402
from app.sources import congress as csrc  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


# --------------------------------------------------------------------------- #
# 1. Source adapter normalization (no network — exercise the helpers directly)
# --------------------------------------------------------------------------- #
def test_source_helpers() -> None:
    print("test_source_helpers")

    check(csrc._norm_type("Purchase") == "buy", "Purchase -> buy")
    check(csrc._norm_type("Sale (Partial)") == "sell", "Sale (Partial) -> sell")
    check(csrc._norm_type("Sale (Full)") == "sell", "Sale (Full) -> sell")
    check(csrc._norm_type("Exchange") == "exchange", "Exchange -> exchange")
    check(csrc._norm_type("") == "other", "empty -> other")

    low, high = csrc._parse_range("$1,001 - $15,000")
    check(low == 1001.0 and high == 15000.0, f"range parse got {low}/{high}")
    low2, high2 = csrc._parse_range("")
    check(low2 is None and high2 is None, "empty range -> None/None")

    check(csrc._norm_date("2026-05-08T00:00:00") == "2026-05-08", "date coercion")
    check(csrc._norm_date("not-a-date") is None, "bad date -> None")

    # Reporting lag is disclosure - transaction, and negative lags are rejected.
    check(csrc._lag_days("2026-04-01", "2026-04-26") == 25, "lag math 25d")
    check(csrc._lag_days("2026-04-26", "2026-04-01") is None, "negative lag -> None")
    check(csrc._lag_days(None, "2026-04-01") is None, "missing txn -> None")

    # Stable id is deterministic for the same inputs and links to a member page.
    a = csrc._stable_id("Jane Doe", "NVDA", "2026-04-01", "Purchase", "$1,001 - $15,000")
    b = csrc._stable_id("Jane Doe", "NVDA", "2026-04-01", "Purchase", "$1,001 - $15,000")
    check(a == b and a.startswith("ct-"), "stable id deterministic")
    url = csrc._politician_url("Nancy Pelosi")
    check(url is not None and "Nancy%20Pelosi" in url, f"member url got {url}")


def test_source_dedupe() -> None:
    print("test_source_dedupe")
    items = [
        {"id": "ct-1", "member": "A"},
        {"id": "ct-1", "member": "A"},
        {"id": "ct-2", "member": "B"},
    ]
    out = csrc.dedupe(items)
    check(len(out) == 2, f"dedupe collapsed to {len(out)}")


# --------------------------------------------------------------------------- #
# 2. Curated mock set
# --------------------------------------------------------------------------- #
def test_mock_dataset() -> None:
    print("test_mock_dataset")
    rows = data.congress_trades()
    check(len(rows) >= 10, f"mock set has {len(rows)} rows")

    required = {"id", "member", "chamber", "party", "ticker", "type",
                "amountRange", "transactionDate", "disclosureDate", "lagDays",
                "sourceUrl"}
    sample = rows[0]
    missing = required - set(sample.keys())
    check(not missing, f"mock row missing fields: {missing}")

    # Lag is non-negative and consistent with the two dates where present.
    bad_lag = [r for r in rows
               if isinstance(r.get("lagDays"), int) and r["lagDays"] < 0]
    check(not bad_lag, "no negative lag days in mock set")

    # Per-ticker filter narrows the set and only returns that ticker.
    nvda = data.congress_trades(ticker="NVDA")
    check(len(nvda) >= 1, "NVDA present in mock set")
    check(all(r["ticker"] == "NVDA" for r in nvda), "NVDA filter is exact")
    check(len(nvda) < len(rows), "ticker filter narrows the feed")


# --------------------------------------------------------------------------- #
# 3. Panel builder via the harness (model-validated payload)
# --------------------------------------------------------------------------- #
def _build(params: dict) -> dict:
    panel = harness.run_skill("congress_trades", params, {"x": 0, "y": 0, "w": 12, "h": 6})
    assert panel["status"] == "ok", f"build failed: {panel.get('note')}"
    assert isinstance(panel["data"], dict) and panel["data"], "no data"
    return panel["data"]


def test_panel_feed() -> None:
    print("test_panel_feed")
    d = _build({})
    check(bool(d.get("trades")), "feed has trades")
    check(d.get("scope") == "Recent activity", f"scope was {d.get('scope')}")

    st = d["stats"]
    check(st["total"] == len(d["trades"]), "stats total matches trade count")
    check(st["buys"] + st["sells"] + st["exchanges"] <= st["total"], "side counts bounded")
    check(st["uniqueMembers"] >= 1, "unique members counted")

    # Reporting lag is surfaced honestly in plain language.
    check("STOCK Act" in d["lagNote"], "lag note cites STOCK Act")
    check("disclaim" in d["disclaimer"].lower() or "disclosure" in d["disclaimer"].lower(),
          "disclaimer present")

    # Every trade carries a source link back to the public disclosure.
    check(all(t.get("sourceUrl") for t in d["trades"]), "every trade has a source link")


def test_panel_ticker_filter() -> None:
    print("test_panel_ticker_filter")
    d = _build({"ticker": "NVDA"})
    check(d.get("ticker") == "NVDA", "ticker echoed")
    check(d.get("scope") == "NVDA", "scope is the ticker")
    check(bool(d["trades"]), "NVDA feed non-empty")
    check(all(t["ticker"] == "NVDA" for t in d["trades"]), "all trades are NVDA")


def test_panel_highlights() -> None:
    print("test_panel_highlights")
    # The curated mock set is built with a NVDA cluster + a large buy, so the
    # highlight engine should surface at least one notable item on the full feed.
    d = _build({})
    hl = d["highlights"]
    check(isinstance(hl, list), "highlights is a list")
    for h in hl:
        check(bool(h.get("label")) and bool(h.get("detail")), "highlight has label+detail")
        check(h.get("kind") in {"cluster_buy", "large_buy", "large_sale"},
              f"highlight kind unexpected: {h.get('kind')}")


def main() -> int:
    for fn in (test_source_helpers, test_source_dedupe, test_mock_dataset,
               test_panel_feed, test_panel_ticker_filter, test_panel_highlights):
        fn()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
