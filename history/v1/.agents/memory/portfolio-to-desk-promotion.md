---
name: Portfolio → strategy desk promotion
description: Promoting a built signal_portfolio panel into a paper-traded strategy, and the compliance/test-stub gotchas it surfaced.
---

# Promote a constructed portfolio into the strategy desk

"paper trade this portfolio" / "track this portfolio" registers the most-recent
`signal_portfolio` panel's holdings as a paper-traded strategy in the lifecycle desk.

- Detection needs BOTH a portfolio/book/holdings reference AND a track/paper/register/promote verb (in `agent.py`). A plain named-strategy command must NOT be hijacked.
- Source of holdings: the latest `signal_portfolio` panel in the session dashboard (`state.get_dashboard`). Long/short signed weights pass through verbatim.
- **Real-data honesty:** carry the portfolio's `excludedNames` + any names dropped during symbol/weight alignment onto the strategy construction (`source="signal_portfolio"`). Pre-filter symbols/weights so they stay aligned, otherwise `derive_target_weights` falls back to signal ranking instead of using the explicit book.
- If no `signal_portfolio` panel exists in the session, pass through (don't fabricate a book).

## Compliance gate is live on every paper_trade
`paper_trade` runs the pre-trade compliance precheck. A concentrated few-name book (e.g. 50/50) trips the default `maxPositionPct=15` and raises `ComplianceBlock`. Any test that builds a paper book must isolate `compliance_store` with permissive limits — see below.

## Test-fixture isolation lesson (tests/test_strategy.py)
- `compliance_store` shares the same `db` module as `strategy_store`; forcing `db_available=lambda:False` routes BOTH to in-memory. Then set `compliance_store._mem_cfg` to `_default_config()` with permissive `limits` (and restore in `finally`), or the gate refuses concentrated test books.
- **Stub close-series must be HISTORICAL (past dates ending today), not future-dated.** The promotion gate counts `trackDays` from the audited snapshot series, falling back to a bootstrap NAV reconstruction (`mark()` in strategy.py) that keeps only closes `>= inception`. A fresh book has `inception==today`; with real (historical) closes it reconstructs ~1 point → `trackDays < minDays(5)` → correctly BLOCKED. A stub that dated closes from today forward kept all points → trackDays cleared the gate and the block test silently passed-then-failed once compliance isolation let it reach the assertion. `test_rebalance.py` already uses the correct `today - n` pattern.
