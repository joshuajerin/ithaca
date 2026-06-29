# Doomberg Agent Init

Read this before using Doomberg MCP.

## What Doomberg Is

Doomberg is a market research, backtest, and paper-trading MCP server for AI agents.
It gives the agent vetted tools for market data, fundamentals, options, macro, flows,
backtests, scenarios, and draft StrategySpecs.

## First Call

After the MCP server is installed and visible in the agent, call:

```text
doomberg.doomberg_init(goal="<the user's market research or strategy goal>")
```

Use the returned `session_id` to keep the work tied to the same Doomberg trace when the
client supports session context.

## How To Work

1. Start with `doomberg_init`.
2. Use `search_skills` to find the smallest relevant tools.
3. Use `describe_skill` before calling a new tool.
4. Use `run_skill` for durable backtests and longer research work.
5. Use direct tools such as `market_get_ohlcv` for quick single-symbol data.
6. Use `propose_strategy` only for validated draft strategies that a human will review.
7. Report freshness, provenance, warnings, and any missing coverage.

## Boundaries

The agent may:

- Read market data.
- Compare fundamentals and flows.
- Run backtests and scenario analysis.
- Draft paper-trading research and StrategySpecs.
- Surface approval items and artifacts.

The agent must not:

- Claim a result without a Doomberg tool response.
- Invent prices, backtest stats, news, ratings, or filings.
- Deploy live strategies.
- Move money.
- Read raw broker credentials.
- Treat paper-trading output as investment advice.

## Default Research Shape

For a single-stock research task, prefer this sequence:

1. `doomberg_init`
2. `market_get_ohlcv`
3. `search_skills(query="fundamentals analyst ratings institutional flows news options volatility")`
4. `describe_skill` for the selected tools
5. `run_skill` or the direct skill tool calls
6. A backtest or scenario run if the user asks for an actionable setup
7. A concise conclusion with provenance and uncertainty

## NOW Try It Out

Run this as a real Doomberg task:

```text
Use Doomberg to research NVDA as a 3-6 month trade candidate. Start with doomberg_init.
Pull current/near-current price context and 1Y OHLCV, compare NVDA against AMD and AVGO on
fundamentals, check recent news, analyst ratings, institutional flows, and options/volatility
signals, then run one momentum-style backtest and one downside stress or scenario. Return a
short trade memo with the data freshness, tool provenance, key risks, and whether the result
supports watchlist, paper trade, or pass.
```
