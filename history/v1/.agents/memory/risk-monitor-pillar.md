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
`DEFAULT_RISK_LIMITS` keys: maxGross, maxNet, maxPosition, maxSector, maxFactor (multiples/fractions) + varLimit (daily VaR fraction). Each limit emits status ok/warn/breach by utilization; `inLimit` is false if any breach. Overridable via the `limits` tool param. Each emitted limit row carries a `key` (the config key) so the UI can map a row back to the config.

## Inline limit editing (refine path)
The panel edits limits live via the existing `/refine` flow, NOT a new endpoint. Key constraint: refine REBUILDS the panel from params, and `positions` is truncated to [:14], so the book can't be reconstructed from displayed data. Fix: `build_risk_monitor` stores an internal `_refine` block in the data dict (full symbols/weights/nav/portfolio_name + current limits + factor/asset shocks). `agent._refine_risk_monitor` runs deterministically BEFORE the LLM path: it parses limit edits (JSON `{"limits":{...}}` or `key=value`) and merges them onto `_refine`'s stored book+limits so a limit edit never resets the book and shocks survive. Non-limit instructions return None → fall through to the normal LLM/heuristic refine. Frontend sends `JSON.stringify({limits:{...}})`; ratio limits edit as the multiple, exp/pct edit as a percent (÷100 to config).

## Why pure-numpy engine separate from skills
Same pattern as factor-risk-model and backtest engine: engine stays IO-free and unit-testable (`tests/test_stress.py`, run directly via `python tests/test_stress.py` — pytest is NOT installed), data assembly lives in skills.

## Refine resets the book (gotcha) + custom shock builder
Panels store NO original params — `agent.refine` rebuilds from only the new params, so a naive risk_monitor refine resets to the default NVDA book. The custom shock builder works around this: the frontend (`RiskMonitorPanel.tsx onShock`) emits a CANONICAL instruction ("Custom shock: factor|asset|market <name> <pct>%"), parsed deterministically in `agent.py` (`_parse_shock` + `_risk_monitor_shock_params`, dispatched BEFORE the LLM in `refine`), which reconstructs symbols/weights/nav/name from `panel.data.positions`+`nav`+`bookName` and merges the shock → `build_risk_monitor` returns the `customStress` slot (already existed, was just never rendered). Title preserved only on this shock path (passing `title` globally would regress other panels' refine, e.g. chart ticker swap). Caveat: positions are capped at 14 in panel data, so books >14 names lose the tail on a shock-refine.

## Agent/voice wiring
Passthrough panel (no openapi codegen — Panel.data is a dict; frontend `RiskMonitorPanel.tsx` declares its own interface). Wired in agent.py: tool `add_risk_monitor`, `_TOOL_TO_TYPE`, `_TYPE_LABELS`, system-prompt routing, heuristic `wants_riskmonitor` (routed BEFORE wants_scenario because they share "stress test"/"shock" keywords), and `_apply_dashboard_scope` pulls on-screen symbols when none given. Voice rides the shared orchestrate path automatically.
