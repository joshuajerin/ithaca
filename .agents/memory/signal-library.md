---
name: Alpha signal library & eval
description: Cross-sectional alpha signal research desk (IC, decay, turnover, quantile spread) — design contract and dispatch rules.
---

# Alpha signal library (signal_research + signal_scorecard)

Pure-numpy cross-sectional signal engine in `app/engine/signals.py`: signals
momentum, short_reversal, low_volatility, value, quality. Eval math = rank IC,
IC decay across horizons, turnover, quantile/decile long-short spread equity curve.

**Real data only:** names/fields that are missing are EXCLUDED and reported in a
coverage footer — never imputed. value uses fval=1/peRatio (pe>0 else excluded
"missing P/E"); quality uses fval=netMargin (None/0.0 excluded).

**Builders return only the panel `data` payload**, not a full Panel. The agent's
`add()` helper / harness wraps it with id/type/title/layout/status. To validate
the route's `response_model=DashboardSpec` offline, get panels from
`agent._orchestrate_heuristic(q)` and wrap in `models.DashboardSpec(...)` — do NOT
feed builder output straight into DashboardSpec.

**Heuristic dispatch (research vs scorecard) is keyword-fragile.** Key trap: the
metric phrase "rank IC" contains "rank", so a bare "rank"/"ranking" compare-intent
falsely routes "momentum signal research" → scorecard. Rule that works:
- scorecard = explicit scorecard phrases, OR compare-words (compare/versus/vs) with
  ≥2 named signals or any signal/alpha mention, OR signal-mention + best/which/leaderboard/ranking AND "signal research" not in query.
- research = "signal research" in query, OR metric kw (rank ic, ic decay, predict returns, cross-sectional, …), OR signal/alpha mention + ≥1 named signal.
Signal dispatch is placed BEFORE wants_factor (factor matches "alpha" too).

**Why:** verifying via curl/$REPLIT_DEV_DOMAIN and FastAPI TestClient both failed —
curl hit proxy path routing, TestClient invoked the real LLM path and hung past the
proxy window. Offline verification path: engine tests (`python tests/test_engine.py`,
no pytest), builder smoke test on live data, and DashboardSpec serialization of
heuristic panels.
