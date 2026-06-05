---
name: Risk Management & Monitoring pillar
description: How the risk_monitor panel is built — book exposures, limits framework, historical crisis replay, hypothetical shock stress.
---

# Risk Monitor pillar (risk_monitor panel)

A risk-desk panel distinct from the factor risk model (decomposition/MCTR) and from scenario (narrative what-if). Three concerns: live exposures + limits, historical crisis replay, hypothetical shocks.

## Layering
- `app/engine/stress.py` — pure numpy, no IO: `factor_shock_pnl` (Σ exposure·shock), `asset_shock_pnl` (Σ weight·shock), `replay_window` (book P&L + drawdown over a real return matrix, returns covered/missing). Reuses `stats.max_drawdown`.
- `app/sources/prices.py::fetch_daily_closes(symbol, start, end)` — Yahoo chart with period1/period2 UNIX seconds → `{iso_date: close}`. This is how crisis windows (2008/2015/2018/2020/2022) get REAL returns; names that didn't trade then come back empty and are flagged missing (e.g. META has no 2008 data), never imputed.
- `app/skills.py::build_risk_monitor` — assembles the book via `_resolve_book` (signed NAV-fraction weights, negative = short, NO renorm so leverage is preserved), exposures, VaR/CVaR from real returns, factor exposures+MCTR via `decompose_portfolio`, limits, and both stress blocks. Registered as SkillDef "risk-monitor" / panel_type "risk_monitor".

## Limits framework
`DEFAULT_RISK_LIMITS` keys: maxGross, maxNet, maxPosition, maxSector, maxFactor (multiples/fractions) + varLimit (daily VaR fraction). Each limit emits status ok/warn/breach by utilization; `inLimit` is false if any breach. Overridable via the `limits` tool param.

## Why pure-numpy engine separate from skills
Same pattern as factor-risk-model and backtest engine: engine stays IO-free and unit-testable (`tests/test_stress.py`, run directly via `python tests/test_stress.py` — pytest is NOT installed), data assembly lives in skills.

## Agent/voice wiring
Passthrough panel (no openapi codegen — Panel.data is a dict; frontend `RiskMonitorPanel.tsx` declares its own interface). Wired in agent.py: tool `add_risk_monitor`, `_TOOL_TO_TYPE`, `_TYPE_LABELS`, system-prompt routing, heuristic `wants_riskmonitor` (routed BEFORE wants_scenario because they share "stress test"/"shock" keywords), and `_apply_dashboard_scope` pulls on-screen symbols when none given. Voice rides the shared orchestrate path automatically.
