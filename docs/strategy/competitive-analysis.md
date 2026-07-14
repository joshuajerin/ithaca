# Ithaca v2 — Internal Competitive Analysis

**Last updated:** 2026-06-18
**Audience:** Founding team, internal only
**Purpose:** Strategic decision-making — where to focus, what to build, what to defend

---

## How to read this

Every section is blunt. Strengths are real. Weaknesses are real. If a competitor is beating us on something, it says so clearly. The goal is accurate threat modeling, not cheerleading.

Competitors are grouped into three tiers:

- **Tier 1 — Primary:** Direct feature overlap across multiple dimensions. These are the companies a prospect would compare us against side-by-side.
- **Tier 2 — Significant:** Deep overlap on one major dimension; light overlap elsewhere. These matter when we expand.
- **Tier 3 — Adjacent:** Infrastructure or niche products we complement, compete with selectively, or should watch.

---

## Tier 1 — Primary Competitors

These three have the most direct feature overlap with Ithaca. Any sales conversation will involve at least one of them.

---

## Unusual Whales

### What they are

Unusual Whales is a retail-to-professional financial intelligence platform built around options flow data sourced directly from OPRA. They launched around 2021 and grew explosively on the back of meme-stock era retail interest in dark pool prints and unusual options activity. By 2024 they had a reported 200,000+ registered users and became the go-to source for congressional trading disclosures and dark pool data for a generation of self-directed traders. The product is primarily a real-time dashboard with alerts, screeners, a news feed, and a data API. Community (Discord, Twitter/X) is integral to the brand — they cross-reference data with narrative in a way that feels like a media company as much as a data company.

### What they do really well

- **Real-time OPRA options flow** with unusually low latency for a retail product — sub-second prints, contract-level granularity, sweep tagging.
- **Congressional trades** are their highest-quality, highest-visibility dataset. They were early, they maintained it, and media outlets cite them.
- **Dark pool / block trade data** — well-visualized, alert-driven, usable by non-quants.
- **Community signal amplification** — they have a self-reinforcing loop where users post trades, others analyze, the platform gets cited in mainstream media, which brings more users.
- **Price point** — $60–$70/month Pro tier is aggressively low for OPRA-sourced data. Most retail users accept this as the ceiling of what good data costs.
- **API tier** — they recently launched a paid API (~$200–$500/month range) that gives developers programmatic access to flow, congressional, and news data.

### What they're missing

- No agent layer. Zero. The data is in a dashboard you click through.
- No backtest. You can see historical flow but cannot run a systematic strategy against it.
- No deploy. Nothing even approximates paper or live trading.
- No MCP surface. You cannot hook their data into Claude, GPT, or any AI agent programmatically without scraping or unofficial wrappers.
- No point-in-time fundamentals. Their fundamental data coverage is shallow.
- No portfolio-level analytics. Individual signals, not portfolio construction.

### Their moat

1. **Congressional trade data** — they have the deepest, most trusted public dataset here. STOCK Act filings are public but their normalization/enrichment is a real product.
2. **Community** — the Discord has tens of thousands of active members. This is tacky to say, but it's a real moat: switching cost is the community, not the software.
3. **Brand/media presence** — cited by Bloomberg, WSJ. Name recognition at the retail-professional boundary.
4. **Data licensing** — OPRA isn't free. They pay for it. A new entrant has to replicate this spend.

### Their pricing

- **Free tier:** Limited flow data, delayed
- **Pro:** ~$60–70/month (exact price floats, has been tested)
- **API:** ~$200–500/month, volume-tiered, terms unclear on redistribution
- **Annual discounts:** ~25% off monthly

### How they'd likely respond to Ithaca

Initially ignore. Their customer is a trader who wants to click through a dashboard, not a developer building an agent. If Ithaca starts eating into their API customer base (developers building tools on top of flow data), they would likely lower API prices and accelerate their own "AI features" roadmap — which at this point probably means adding a chatbot to the dashboard, not a real MCP surface. Congressional trades are a political/PR win for them; they'd defend it hard.

### Where Ithaca beats them

- **MCP-native programmatic access** — an AI agent can call Ithaca's `congress_trades`, `options_greeks`, `sentiment_get` etc. tools directly. No scraping, no unofficial API.
- **Backtesting** — you can test whether that unusual options activity actually predicted price movement using our backtest engine.
- **Full workflow** — from signal (options flow / congressional trade) → research → backtest → paper deploy. Unusual Whales has no workflow; it's discrete data views.
- **Audit trail** — every tool call is tenant-isolated and traced. Useful for compliance-conscious users.

### Where they beat Ithaca

- **Real-time OPRA data** — our options data is delayed or sourced downstream; theirs is direct OPRA. This is a meaningful gap for intraday traders.
- **Dark pool / block prints** — we don't have this data at all currently.
- **Community** — they have a massive, engaged user base that generates secondhand signal.
- **Price** — their dashboard is cheap. Ithaca will be priced higher and will need to justify it.
- **Brand recognition** — retail traders know Unusual Whales. Ithaca is new.

### The customer who would choose them over Ithaca

A retail day trader or swing trader who watches options flow manually, wants mobile alerts on unusual activity, participates in the Discord to cross-reference community commentary, and has no interest in building automated systems. They want curated human-readable alerts, not an API.

### The customer who would choose Ithaca over them

A developer or quant who wants to give their AI agent access to options flow + congressional trades + fundamentals as part of a systematic research or trading pipeline. They need MCP endpoints, not a dashboard. They want to backtest whether the congressional trade signal has alpha. They need tenant isolation for multi-client use.

---

## QuantConnect / Lean

### What they are

QuantConnect is the leading open-source cloud backtesting and live execution platform for algorithmic traders. Founded in 2013, they built LEAN — an open-source C#/Python backtesting engine that has become the de facto standard for retail and semi-professional quant work. The hosted platform runs backtests at scale, has a research environment (Jupyter-based), and connects to a large number of brokers for live execution. They have a reported 250,000+ registered users and a strong institutional arm (QuantConnect Alpha Streams, where algorithms are sold to hedge funds).

### What they do really well

- **LEAN engine quality** — genuinely excellent. Handles tick, minute, daily. Has realistic slippage, commission, and fill models. Handles survivorship bias correctly for equities (with paid data).
- **Broker integrations** — 15+ live brokers. The deployment layer for live trading is production-grade.
- **Data library** — they have licensed minute-bar US equity data going back to ~1998 via their marketplace. Options data available. Crypto. Futures.
- **Research environment** — Jupyter notebooks with factor analysis, tearsheets, Pyfolio integration.
- **Open source LEAN** — self-hosting is possible. This is a real moat; contributors extend it, and defectors still use the engine.
- **Algorithm Marketplace** — you can sell your algorithm or license data. Network effects.

### What they're missing

- No MCP surface. You write Python or C#; you cannot call LEAN from an AI agent without custom tooling.
- No BYO agent paradigm. The agent is you, writing code in their IDE.
- No real-time observability UI for AI reasoning. You see P&L and orders, not agent thought process.
- The research → deploy workflow requires significant code. No declarative StrategySpec equivalent.
- Their "AI" features are nascent — some LLM-assisted code generation, nothing agent-native.
- UI is dated and hard to onboard. Significant learning curve for non-coders.

### Their moat

1. **LEAN engine** — 10+ years of battle-testing. It is the most trusted open-source backtest engine. Competitors have to argue against an open-source default.
2. **Data partnerships** — they have licensed institutional-grade data. This took years and significant capital to assemble.
3. **Community and talent** — their forums are active, their documentation is extensive, and their reputation in the quant community is strong.
4. **Alpha Streams** — the ability to monetize your algorithm creates retention that pure tools cannot.

### Their pricing

- **Free:** 1 backtest job at a time, shared compute, limited data
- **Researcher:** ~$8/month — more compute
- **Team:** ~$20/month — more parallel jobs
- **Trading Firm:** ~$80/month — full live trading support
- **Data add-ons:** US Equity data from $10–200+/month depending on resolution

### How they'd likely respond to Ithaca

Build an MCP adapter for LEAN. This is technically straightforward — expose backtest_run as an MCP tool, publish it. They have the engineering resources. Their risk is that they do this slowly because their roadmap is driven by the quant coder audience, not the "AI agent" audience. If Ithaca gains traction with developers building AI trading agents, QuantConnect would notice and add MCP endpoints within 12–18 months. They would frame it as "LEAN for AI agents."

### Where Ithaca beats them

- **BYO agent paradigm** — Ithaca has no opinion about what agent you use. QuantConnect owns the execution environment.
- **Onboarding speed** — a declarative StrategySpec and an MCP call is faster to prototype than writing LEAN Python.
- **Research tool breadth** — 29 tools covering flow, congressional, sentiment, macro, options surface. QuantConnect's research is mostly price/fundamental.
- **Observability** — 3-column trace of agent reasoning + tool calls + evidence is unique. QuantConnect shows P&L curves, not agent thinking.
- **Human-gated money path** — explicit promote → activate → live with manual gate. QuantConnect trusts you to configure your own risk controls.

### Where they beat Ithaca

- **Backtest engine depth** — LEAN handles tick data, options pricing at fill time, multi-leg combos, realistic execution models. Our backtest engine is not at this level.
- **Live execution breadth** — 15+ brokers. We have paper trading and Alpaca seam; full live execution is not shipped.
- **Data depth** — their licensed data library for US equities is far deeper historically.
- **Credibility with serious quants** — QuantConnect is trusted. Ithaca is unproven.
- **Open source** — LEAN is forkable. Ithaca is a hosted service.

### The customer who would choose them over Ithaca

A systematic quant trader who writes Python, wants rigorous backtesting with tick-level realism, plans to connect to a broker for live execution, and needs to run 50+ parallel backtests. They will write their own research code and don't need an AI agent layer.

### The customer who would choose Ithaca over them

A developer building an AI agent that should be able to conduct financial research and propose/test/paper-trade strategies — but who doesn't want to become an expert in LEAN. They want to call `backtest_run` with a JSON spec, not manage a LEAN codebase. They may serve multiple tenants and need isolation + audit trails.

---

## Bloomberg Terminal

### What they are

The Bloomberg Terminal (Bloomberg Professional Service) is the dominant institutional financial data and analytics platform, operated by Bloomberg LP (private, ~$6B revenue). It runs on dedicated hardware (or a VM), provides real-time price data for virtually every liquid asset globally, news, messaging (IB Chat), analytics, Excel integration (BLPAPI), and deep fundamental data including point-in-time financials. As of 2024, approximately 325,000 terminals are in use globally at hedge funds, banks, asset managers, and corporates. It is the infrastructure layer that the financial industry is built on.

### What they do really well

- **Data comprehensiveness and quality** — there is genuinely no peer. FX, rates, equities, credit, commodities, derivatives, structured products. Real-time, tick-level.
- **Point-in-time fundamentals** — Bloomberg's PIT data is trusted for backtesting by institutions. No survivorship bias, correct as-reported figures.
- **BQuant** — Bloomberg's cloud Python environment for quant research. Jupyter notebooks with direct BLP API access. Legitimately good.
- **BLPAPI** — a proper programmatic API used by every major hedge fund. Python, Java, C++ SDKs.
- **News** — their news wire (BN) is fast and complete. First-party reporting, plus aggregation.
- **IB messaging** — the Bloomberg chat network is a market microstructure asset. Deals are sourced on IB.

### What they're missing

- **MCP surface** — zero. BLPAPI is not an MCP endpoint. You can build one, but Bloomberg will not provide it.
- **BYO agent paradigm** — BQuant is their answer to AI-assisted research, but it's their environment, their models.
- **Affordability** — $25k/year/seat means most of their users are at institutions, not independent developers or small funds.
- **Deploy layer** — Bloomberg has order management (BSKT, EMSX) but it's complex, institutional, and not a "deploy your AI strategy to paper trading" workflow.
- **Retail accessibility** — deliberately excluded from their strategy.

### Their moat

1. **Data depth and trust** — 40+ years of clean, institutional-grade data. No one has replicated this.
2. **Network effects** — IB messaging, the terminal as the shared medium of institutional finance.
3. **Switching cost** — workflows, proprietary functions (BDH, BDP), Excel models built over decades. Churning is career risk.
4. **Price** — perversely, $25k/seat creates an exclusivity signal. Institutions that can't afford it signal their size.

### Their pricing

- **Standard terminal:** ~$25,000/year/user (2-seat minimum for new subscribers)
- **BQuant:** Available at enterprise pricing on top of terminal
- **BLPAPI:** Included with terminal subscription
- **No self-serve tier.** Sales-driven only.

### How they'd likely respond to Ithaca

They won't, initially. Ithaca's target customer is not a Bloomberg subscriber. If AI-native financial tools start pulling institutional buy-side away from terminals (e.g., hedge funds replacing terminal seats with AI agents), Bloomberg would build their own MCP surface on top of BLPAPI. They have the engineering resources. They are not sleeping — Bloomberg already has an internal AI push (2024 GPT-4-based earnings call analysis, etc.). But organizational inertia is real; an MCP adapter for BLPAPI would likely take 2–3 years to reach GA.

### Where Ithaca beats them

- **Price** — orders of magnitude cheaper. An independent developer or small fund can access Ithaca; they cannot afford Bloomberg.
- **MCP-native** — Ithaca's tools are MCP endpoints from day one. Bloomberg's API requires custom integration.
- **BYO agent** — bring Claude, GPT, or your own model. Bloomberg's AI features use Bloomberg's models.
- **Workflow** — research → backtest → paper deploy in one platform. Bloomberg has the research half; deploy is complex and institutional.
- **Onboarding** — self-serve. Bloomberg requires a sales contract.

### Where they beat Ithaca

- **Everything data-related** — depth, breadth, quality, latency, history.
- **Institutional trust** — Bloomberg data is what funds' compliance teams have approved.
- **Real-time** — their real-time data is genuinely real-time at institutional level.
- **Ecosystem** — Excel integration, IB messaging, OMS connectors — decades of workflow built in.
- **PIT fundamentals** — Bloomberg's point-in-time is the gold standard.

### The customer who would choose them over Ithaca

An institutional portfolio manager or analyst at a fund, bank, or large asset manager who needs real-time fixed income pricing, Bloomberg chat access, the full FIGI/SEDOL universe, and whose firm's compliance policy mandates Bloomberg-sourced data.

### The customer who would choose Ithaca over them

An independent developer, small fund ($10M–$500M AUM), or fintech building AI-native financial tooling who needs good-enough data + MCP endpoints + backtest + paper trading at a price point that doesn't require a 2-seat minimum Bloomberg contract. They want to give their Claude or GPT agent access to financial tools, not manage a Bloomberg terminal subscription.

---

## Tier 2 — Significant Overlap on One Dimension

These competitors each overlap Ithaca on one critical capability. They're important to understand but less likely to be a direct head-to-head comparison unless Ithaca expands into their core.

---

## Koyfin

### What they are

Koyfin is a financial charting, fundamentals, and macro research platform that launched around 2018 as a Bloomberg-lite alternative for self-directed investors and independent analysts. They focus on usability — their charting is genuinely cleaner than Bloomberg's, their macro dashboard is popular, and their screener is strong. They raised a Series A (~$20M) and have been growing steadily. Target user is the independent financial analyst, RIA associate, or sophisticated retail investor who finds Bloomberg unaffordable and Yahoo Finance too shallow.

### What they do really well

- Clean, fast charting UI. Better UX than any institutional product.
- Macro dashboard with 500+ economic series from FRED, ECB, BLS — well-organized.
- Fundamentals coverage is solid for US and global equities.
- Screener has useful filters (FCF yield, EV/EBITDA, etc.).
- Watchlist and notes features create daily-use stickiness.
- Price point is competitive: ~$49/month for Pro.

### What they're missing

- No agent layer, no API, no MCP surface.
- No backtest. No deploy.
- No options flow, no congressional data, no insider data.
- No programmatic access to their data. It's a read-only dashboard.

### Their moat

Good UX and price positioning. They're in the "Bloomberg alternative" category. Moat is moderate — the data itself is licensed from standard sources; anyone can license the same feeds.

### Their pricing

- **Free:** Very limited
- **Plus:** ~$25/month
- **Pro:** ~$49/month
- **Expert:** ~$79/month (more data, more history)

### How they'd likely respond to Ithaca

Ignore. Their roadmap is UI-first. They might add "AI features" (ask a chatbot about your portfolio), but MCP-native tooling for BYO agents is unlikely from this team in the near term.

### Where Ithaca beats them

Programmatic access, MCP endpoints, backtest, deploy, options data, congressional/insider data. Koyfin has none of these.

### Where they beat Ithaca

UI/UX quality, macro data breadth, charting quality, established user base, onboarding simplicity. Koyfin is a better reading/research experience for a human analyst.

### The customer who would choose them over Ithaca

An independent equity analyst or RIA who wants to research 20 stocks a day, build watchlists, chart macro indicators, and write reports. No automation, no agent.

### The customer who would choose Ithaca over them

A developer building an AI agent that needs to call fundamentals, macro, or screener data programmatically as MCP tools.

---

## Quiver Quantitative

### What they are

Quiver Quantitative is an alternative data API platform focused on non-traditional financial signals: congressional trades, government contracts, lobbying, satellite data (parking lots, etc.), web traffic, social media sentiment, and insider transactions. Founded ~2020 by two college students, they have grown to a meaningful API subscriber base. Their niche is providing signals that aren't in traditional financial data vendors. Strong developer community and good Python SDK.

### What they do really well

- **Congressional trades** — deep dataset, well-maintained, goes back years. Probably the most comprehensive source outside government filings themselves.
- **Alternative data breadth** — lobbying, patents, government contracts, satellite imagery — a genuinely differentiated set.
- **Developer-friendly API** — clean REST endpoints, good docs, free tier with generous limits.
- **Pricing** — free tier is usable; paid plans start at $50–$100/month.

### What they're missing

- No backtest, no deploy. Just data.
- No MCP surface (as of mid-2026).
- Fundamentals and price data are not their focus — you have to combine with other sources.
- No options flow, no macro.

### Their moat

The alt data assembly itself. Congressional trades, lobbying, and satellite data are painful to aggregate at scale. Their normalization is the product. Small but real moat.

### Their pricing

- **Free:** Limited daily calls
- **Individual:** ~$50/month
- **Professional:** ~$100–200/month
- **Institutional:** Custom

### How they'd likely respond to Ithaca

Build MCP wrappers for their API. This is one developer's weekend project; the schemas exist. If Ithaca gains traction as a tool platform, Quiver could position as a data provider that plugs into Ithaca. More likely: they build MCP tools and compete on alt data depth.

### Where Ithaca beats them

MCP-native tools that don't require the user to build their own wrappers, backtest integration so you can test whether the congressional signal has alpha, full workflow.

### Where they beat Ithaca

Alt data breadth (lobbying, patents, government contracts, satellite). We don't have this data.

### The customer who would choose them over Ithaca

A quant researcher who wants raw alt data signals in a Pandas DataFrame and will do their own analysis.

### The customer who would choose Ithaca over them

A developer who wants congressional + insider data available as MCP tools for their AI agent without building wrappers, and who also needs backtest/deploy in the same platform.

---

## Composer

### What they are

Composer is a no-code systematic trading platform — the closest thing to a retail-accessible "strategy deployment" product. Founded ~2020, they let users build strategies with a visual editor (flowchart-style logic), backtest them against historical data, and deploy to live execution through Alpaca. Their pitch is "hedge fund strategies for everyone." They raised ~$12M. Target user is a non-coder retail investor who wants systematic exposure without writing code.

### What they do really well

- **No-code strategy builder** — genuinely usable by non-coders. Drag-and-drop conditional logic.
- **Backtest + live deploy in one flow** — the workflow from build → test → paper → live is smooth.
- **Alpaca execution** — clean Alpaca integration, real live trading for US equities and ETFs.
- **Template library** — pre-built strategies (momentum, factor, rotation) that users can clone.
- **Price** — $19–29/month. Very accessible.

### What they're missing

- No BYO agent. No AI. Their AI plans are limited to suggestions within their builder.
- No MCP surface.
- Limited data — US equities and ETFs only, daily bars. No options, no alternative data.
- Strategy logic is constrained by their visual editor. Complex strategies aren't expressible.
- No observability. You see P&L, not reasoning.

### Their moat

UX and distribution. They've made "systematic trading" feel non-threatening to retail investors. Moat is defensible only if they keep the UX lead — the underlying data/execution is not proprietary.

### Their pricing

- **Free:** Limited backtests
- **Basic:** ~$19/month
- **Pro:** ~$29/month

### How they'd likely respond to Ithaca

This is the most interesting competitive response. Composer could add an "AI strategy builder" mode where you describe a strategy in natural language and it gets translated to their execution graph. That would address the "BYO agent" gap. However, their architecture is fundamentally visual/no-code — retrofitting MCP tool calls would require significant engineering. More likely they add a chatbot wrapper around their existing builder.

### Where Ithaca beats them

BYO agent paradigm (you bring the intelligence), data depth (options, alt data, fundamentals PIT), backtest sophistication, observability, multi-asset beyond US equities/ETFs.

### Where they beat Ithaca

UX for non-coders, live execution (they have it; we don't fully), price point, established user base for systematic retail trading.

### The customer who would choose them over Ithaca

A retail investor who wants to automate their momentum strategy on ETFs, doesn't code, and wants a clean UI to do it in 20 minutes without an API key.

### The customer who would choose Ithaca over them

A developer building an AI agent that should research, backtest, and propose systematic strategies with full audit trail. They need MCP endpoints and want to bring Claude or GPT as the strategy brain.

---

## Alpaca

### What they are

Alpaca is a commission-free brokerage API platform for developers — the execution layer for algorithmic trading apps. Founded 2015, launched trading API 2018. They provide paper and live trading for US equities, options, and crypto. Many fintech products (Composer, various robo-advisors) are built on top of Alpaca as their execution layer. They don't provide data tools, research, or backtest engines — pure execution.

### What they do really well

- **Brokerage API quality** — reliable, well-documented, good Python/JS SDKs.
- **Paper trading** — free, realistic simulated execution, same API as live.
- **Options API** — added options trading support, relatively rare for a developer-first broker.
- **Broker-dealer infrastructure** — they handle the compliance/clearing. This is hard to replicate.
- **Free for low-frequency trading** — no minimums, no per-trade cost for basic use.

### What they're missing

- Everything above the execution layer. No data, no research, no backtest, no observability.
- No agent framework.
- Not a data/analytics product at all.

### Their moat

Broker-dealer licensing is a genuine regulatory moat. Getting a FINRA BD license, building clearing relationships, and handling SIPC coverage is 2–3 years of work minimum. This is the hardest part of the execution stack to replicate.

### Their pricing

- **Paper trading:** Free
- **Live trading:** Commission-free for equities; options: $0.65/contract
- **Data subscriptions:** ~$9–29/month for real-time data (separate from trading)

### How they'd likely respond to Ithaca

Alpaca is a potential partner, not primarily a competitor. They're the execution layer we'd plug into. However, if Ithaca gained significant traction and decided to build execution natively, Alpaca would be irrelevant in that scenario. Their response to an agent-native trading platform would likely be to partner (offer Ithaca as a preferred execution layer) rather than compete.

### Where Ithaca beats them

Research, data, backtest, observability, strategy workflow — everything above order submission.

### Where they beat Ithaca

Execution infrastructure, broker-dealer licensing, options clearing, live trading reliability. We are not and should not try to be a broker.

### The customer who would choose them over Ithaca

A developer who has their own research and strategy code and just needs a reliable, cheap API to execute orders. They don't want a platform, just a brokerage endpoint.

### The customer who would choose Ithaca over them

A developer who wants a full workflow from AI agent research → backtest → paper trading with observability. They'd use Alpaca as the execution seam inside Ithaca, not as a standalone.

---

## AlphaSense

### What they are

AlphaSense is an AI-powered financial research platform specializing in document search and analysis — earnings call transcripts, SEC filings, broker research, news, trade journals. Founded 2011, they've raised ~$1B+ and are used by Fortune 500 companies, hedge funds, and investment banks. Their core product is NLP-powered search over a proprietary corpus of financial documents. Recent expansions include a "Market Intelligence" product and an AI assistant (Smart Summaries) layered on top.

### What they do really well

- **Document corpus** — they have licensed broker research reports that are not publicly available. This is a real differentiator.
- **Earnings call search** — searching across 10 years of earnings calls for a specific topic or management guidance is excellent.
- **NLP quality** — their entity extraction and financial NLP is mature after 15+ years.
- **Enterprise integrations** — Salesforce, Slack, workflow tools.
- **Smart Summaries** — their LLM summaries of earnings calls and filings are genuinely high-quality.

### What they're missing

- No backtest, no deploy, no trading at all.
- No real-time price data.
- No options flow, no congressional data.
- No MCP surface (as of mid-2026).
- Very expensive for individual use — primarily enterprise pricing.

### Their moat

Licensed broker research is the core moat. They have agreements with 100+ sell-side firms. Replicating this takes years of business development. Their document corpus is genuinely difficult to replicate.

### Their pricing

- **Enterprise only** — pricing typically $15,000–$50,000+/year depending on seats and corpus access
- No public self-serve tier at meaningful functionality

### How they'd likely respond to Ithaca

They wouldn't see Ithaca as a threat — we're targeting developers; they're targeting enterprise analysts. If Ithaca started productizing LLM-assisted document analysis over SEC filings/earnings calls, AlphaSense would have legitimate grounds to consider it competition. Their response would be enterprise sales muscle, not product development.

### Where Ithaca beats them

Price (orders of magnitude), MCP-native access, backtest + deploy, options/alternative data. For anything outside document analysis, Ithaca is more capable.

### Where they beat Ithaca

Document corpus (especially licensed broker research), earnings call search quality, enterprise integrations, regulatory document coverage, institutional trust.

### The customer who would choose them over Ithaca

An equity research analyst at a hedge fund or investment bank who needs to search across 10 years of earnings calls for a theme, read broker research, and generate summaries. They don't code; they do fundamental analysis.

### The customer who would choose Ithaca over them

A developer building an AI agent that needs MCP tools for financial data + backtest + paper trading. AlphaSense has no relevance to this use case.

---

## Tikr Terminal

### What they are

Tikr Terminal is a fundamentals-focused financial research platform built for equity analysts and long-only investors. Strong deep fundamental data coverage (10+ years of financials, global coverage), SEC filings integration, built-in DCF modeling templates, and peer comparisons. Launched ~2020, positioned as a Bloomberg/FactSet alternative for fundamental investors. Freemium to ~$30/month paid tier.

### What they do really well

- **Historical fundamentals depth** — 10+ years, clean, for global equities including small-caps.
- **Integrated DCF** — users can build and save DCF models within the platform, adjust assumptions, see sensitivity.
- **Filing viewer** — inline SEC filing annotation alongside financial data.
- **Price** — free tier is legitimately useful; paid is cheap.

### What they're missing

- No API, no programmatic access, no MCP.
- No backtest, no deploy.
- No real-time or near-real-time data.
- No agent layer.
- No options, no alt data.

### Their moat

Price and simplicity for fundamental analysts. Not a strong technical moat — their data is licensed from standard providers.

### Their pricing

- **Free:** Limited but usable
- **Pro:** ~$30/month

### How they'd likely respond to Ithaca

They are not a competitor in any meaningful sense. Tikr is a reading/analysis tool for fundamental investors. They won't build MCP endpoints or backtest engines.

### Where Ithaca beats them

Programmatic access, everything systematic, agent-native workflow.

### Where they beat Ithaca

UI quality for manual fundamental analysis, DCF model templates, filing annotation, global small-cap fundamentals coverage.

### The customer who would choose them over Ithaca

A value investor who does manual DCF models, reads 10-Ks, and wants a clean interface to pull historical income statements globally.

### The customer who would choose Ithaca over them

Anyone building a systematic or AI-assisted research workflow.

---

## Perplexity Finance

### What they are

Perplexity is an AI search engine that added a "Finance" vertical in 2024 — real-time stock quotes, news summaries, earnings snapshots, and AI-generated financial research answers. It is powered by their Sonar model and web crawling, not licensed institutional data. As of 2026 they have 50M+ monthly active users and enormous distribution. Finance mode is a feature, not a standalone product.

### What they do really well

- **Distribution** — enormous existing user base. Finance is a free feature upgrade for existing users.
- **Answer quality for research questions** — for "what is the current sentiment on NVDA" or "what happened to TSLA earnings" they give fast, readable answers.
- **Real-time web crawling** — recent news is included in answers.
- **Price** — free for most use cases.

### What they're missing

- No structured data API for financial metrics.
- No backtest, no deploy.
- No options flow, no congressional data, no point-in-time fundamentals.
- No MCP surface (as of mid-2026 — though Perplexity has published MCP tools for web search, not Finance).
- Data quality/sourcing is web scraping, not licensed institutional data.

### Their moat

Distribution and brand. The finance feature rides on Perplexity's existing moat, not on financial data investments.

### Their pricing

- **Free:** Unlimited basic searches
- **Pro:** ~$20/month (includes more powerful models, Pro Search)

### How they'd likely respond to Ithaca

Perplexity has little reason to respond. Their Finance feature targets the curious retail investor who wants quick answers, not systematic traders. If Ithaca launched an AI research interface, Perplexity would not see it as a threat. They might publish MCP tools for their Finance data in the future — which would be relevant to Ithaca.

### Where Ithaca beats them

Structured, licensed financial data, backtest, deploy, options/alt data, MCP tools callable by agents, audit trail.

### Where they beat Ithaca

Distribution (50M+ users vs. zero), brand recognition, breadth of general research questions, real-time web crawling for news.

### The customer who would choose them over Ithaca

Someone who wants a quick answer to "what's happening with AAPL this week" and doesn't need an agent pipeline or backtest.

### The customer who would choose Ithaca over them

A developer whose AI agent needs structured, reliable financial data via MCP tools. Perplexity gives prose; Ithaca gives JSON that an agent can act on.

---

## Tier 3 — Adjacent / Niche

These competitors overlap Ithaca on a specific, narrow dimension. Understanding them matters for data sourcing, partnership strategy, and preventing flank attacks.

---

## Polygon.io

### What they are

Polygon.io is a financial market data API provider — raw OHLCV for US equities, options, forex, and crypto. Founded 2018, developer-friendly, REST + WebSocket APIs, fast, reliable. They are infrastructure, not a product. Many fintech tools (including potentially Ithaca) are built on top of Polygon's data.

### What they do really well

- **Data reliability and uptime** — Polygon is trusted by a large developer community.
- **Breadth** — equities, options, crypto, forex. Historical and real-time.
- **Price** — free tier is generous for development; paid tiers are reasonable ($29–$199+/month).
- **Developer experience** — clean docs, good SDKs, Polygon WebSocket for real-time.

### What they're missing

- No compute layer — just raw data.
- No backtest, no deploy, no agent tools.
- No alternative data.

### Their moat

Data reliability and developer mindshare. They've become a standard infrastructure choice.

### Their pricing

- **Free:** 5 API calls/minute, delayed data
- **Starter:** $29/month — unlimited calls, 15-min delay
- **Developer:** $79/month — real-time
- **Advanced:** $199+/month — options real-time, high volume

### How they'd likely respond to Ithaca

Polygon is a potential data supplier for Ithaca, not a competitor. They might publish MCP tools for their API — but raw OHLCV via MCP is not a product, it's infrastructure.

### Where Ithaca beats them

Everything above data delivery — research tools, backtest, deploy, observability.

### Where they beat Ithaca

Raw data latency, data breadth for prices, developer reliability, price for pure data access.

### The customer who would choose them over Ithaca

A developer who has their own research/backtest pipeline and just needs a reliable, cheap price data API.

### The customer who would choose Ithaca over them

A developer who wants data + compute + agent tools in one platform.

---

## Danelfin

### What they are

Danelfin is an AI stock scoring platform that assigns AI scores (0–10) to US and European stocks based on 900+ technical, fundamental, and sentiment features. Founded ~2019. They publish daily scores and have a web app and API. They train their own models; users cannot bring their own AI.

### What they do really well

- Comprehensive feature set behind each score — transparent about what drives the rating.
- European stock coverage (unusual for retail-grade AI tools).
- Clean API with reasonable pricing.

### What they're missing

- No BYO agent. Their AI is their AI.
- No backtest, no deploy.
- No options flow, no alt data.
- MCP surface: none.

### Their moat

Proprietary model trained on 900+ features. Switching cost is low — it's a score on a dashboard.

### Their pricing

- **Free:** 5 stocks/day
- **Pro:** ~$30–50/month
- **API:** ~$100–300/month depending on volume

### How they'd likely respond to Ithaca

Not a response. Different target customer. Danelfin serves investors who want to know "what's a good stock to buy," not developers building agent pipelines.

### Where Ithaca beats them

Programmatic MCP access, BYO agent, backtest, workflow.

### Where they beat Ithaca

Pre-built AI signals for users who don't want to build their own research pipeline. Faster for a human to consume.

### The customer who would choose them over Ithaca

A non-technical investor who wants AI-generated stock picks without building anything.

### The customer who would choose Ithaca over them

A developer who wants to build their own scoring logic using raw data and their own AI model, then backtest it.

---

## Tickeron

### What they are

Tickeron is an AI-powered technical analysis and pattern recognition platform targeting retail traders. They offer AI-driven "Confidence Score" for technical breakouts, trend predictions, and trading bot templates. Founded ~2016.

### What they do really well

- Pattern recognition (head and shoulders, wedges, etc.) with quantified historical accuracy.
- Pre-built trading bots accessible to non-coders.
- Active community and educational content.

### What they're missing

- Closed AI — no BYO agent, no MCP.
- No fundamental data, no alt data.
- No rigorous backtest (their "AI predictions" are backtested internally but not user-definable).
- Paper trading is limited.

### Their moat

Retail brand recognition in the technical analysis space. Not a deep technical moat.

### Their pricing

- **Basic:** Free
- **Investor:** ~$90/month
- **Trader:** ~$150/month
- **Premium:** ~$350/month

### How they'd likely respond to Ithaca

No response. Entirely different customer and architecture philosophy.

### Where Ithaca beats them

Data quality, BYO agent, MCP surface, backtest rigor, fundamentals, alt data.

### Where they beat Ithaca

Pre-built pattern recognition, retail UX, no-code bots, educational content.

### The customer who would choose them over Ithaca

A retail trader who wants technical AI signals with no coding and no API.

### The customer who would choose Ithaca over them

A developer who wants to build and test systematic strategies with full data access.

---

## YCharts

### What they are

YCharts is a fundamentals and charting platform primarily targeting Registered Investment Advisors (RIAs), financial planners, and independent analysts. They provide fundamentals, economic data, fund data, and charting with client-ready presentation features (PDF exports, model portfolios). Founded ~2009, profitable, niche-but-sticky.

### What they do really well

- **RIA workflow integration** — built for investment committees and client presentations.
- **Mutual fund and ETF data** — thorough coverage beyond what most platforms offer.
- **Economic data screeners** — 4,000+ economic series with clean visualization.
- **Client reporting** — PDF generation, benchmarking, model portfolios.

### What they're missing

- No agent layer, no API of note.
- No backtest, no deploy.
- No options flow, no alt data.
- Expensive for what it is.

### Their moat

RIA distribution and workflow stickiness. RIAs build compliance workflows around YCharts reports.

### Their pricing

- **Individual:** ~$150–300/month
- **Team:** Custom, ~$2,000–10,000/year

### How they'd likely respond to Ithaca

No response. Entirely different segment (RIAs vs. developers/quants).

### Where Ithaca beats them

Programmatic access, BYO agent, backtest, alt data, developer-friendliness.

### Where they beat Ithaca

RIA compliance workflow, client reporting, mutual fund/ETF data depth, established RIA relationships.

### The customer who would choose them over Ithaca

An RIA or financial advisor who needs to build client-facing reports and manage model portfolios in a compliance-friendly environment.

### The customer who would choose Ithaca over them

A developer building AI-native financial analysis tooling.

---

## FinancialDatasets.ai

### What they are

FinancialDatasets.ai is the most architecturally similar competitor to Ithaca — a financial data MCP server. They provide MCP tools for financial data (primarily fundamentals: income statements, balance sheets, cash flows, prices) callable by AI agents. Founded ~2024. Self-described as "financial data for AI agents." They appear to be a small team, likely 1–3 people, and are positioned as a data layer without the research depth, backtest, or deploy capabilities of Ithaca.

### What they do really well

- **Same architectural bet** — MCP-native financial data is the right architecture. They validated it.
- **Clean tool definitions** — their MCP tools are well-structured for LLM consumption.
- **Fast to integrate** — developers can get fundamentals into their AI agent in minutes.
- **Lower price barrier** — their pricing is designed for indie developers.

### What they're missing

- Breadth — primarily fundamentals (income statement, balance sheet, cash flow, prices). No options flow, no congressional data, no insider data, no alt data, no macro.
- No backtest. No deploy. No paper trading.
- No observability layer.
- No tenant isolation (as best as can be determined externally).
- No human-gated money path.
- Small team — shipping velocity and data quality maintenance is a real risk.

### Their moat

First mover on the "financial data via MCP" positioning. Developer mindshare if they capture it early. Data moat is minimal — they're using publicly accessible financial data APIs.

### Their pricing

- **Free tier:** Limited calls
- **Paid:** ~$30–100/month based on usage (approximate — their pricing page updates)

### How they'd likely respond to Ithaca

This is the competitor that would most directly feel Ithaca as a threat. They would likely respond by:
1. Expanding data breadth (add options, congressional, insider).
2. Marketing heavily on "simplicity" — we're just data, no opinionated platform.
3. Potentially being acquired by a larger data vendor or broker (Polygon, Alpaca) who wants to compete in the MCP space.

### Where Ithaca beats them

Data breadth (29 tools vs. their ~5–8 tools), backtest engine, paper trading deploy, observability, tenant isolation, human-gated money path, and the full research-to-deploy workflow.

### Where they beat Ithaca

Simplicity — if you just want fundamentals in your AI agent, they're faster to integrate. Lower price point. Potentially better for developers who don't need the full platform.

### The customer who would choose them over Ithaca

An indie developer building a simple AI assistant that can answer "what's AAPL's P/E ratio" and doesn't need backtest or deploy.

### The customer who would choose Ithaca over them

A developer building a serious AI trading agent that needs the full research toolkit, backtest validation, paper trading observation, and multi-tenant isolation.

---

## Strategic Positioning Summary

**Where Ithaca sits in the landscape:**

Ithaca occupies a currently empty position at the intersection of three trends:
1. **AI agents calling financial tools** (no one has built the right MCP surface)
2. **Systematic strategy deployment accessible to developers** (not just quant coders)
3. **Human-in-the-loop trust layer** for AI money management (nobody has designed this correctly)

The clearest wedge opportunities, in priority order:

**Wedge 1: The "MCP-native Bloomberg alternative for developers"**
Bloomberg has everything but is closed, expensive, and not agent-friendly. QuantConnect has backtest/deploy but no research depth and no MCP. Ithaca can be the first platform where an AI agent can do Bloomberg-grade research AND backtest AND deploy — all via standard MCP calls. The target customer is a developer building an AI financial agent and needing a one-stop MCP tool platform.

**Wedge 2: Congressional/insider/alt data accessible to agents**
Unusual Whales and Quiver Quantitative have the data but no MCP surface and no backtest. Ithaca can be the place where an AI agent calls `congress_trades`, validates the signal with `backtest_run`, and proposes a strategy for paper trading — in a single agent loop. This is a workflow no competitor supports today.

**Wedge 3: The "trust layer" for AI trading proposals**
No competitor has a human-gated money path by design. As regulators and institutions start asking "how do you prevent your AI agent from self-trading without oversight," Ithaca's promote → activate → live → pause workflow is a defensible architectural position. This is most relevant in the 12–24 month timeframe as AI trading regulation emerges.

---

## Biggest Threats

Ranked by (likelihood × severity):

**1. FinancialDatasets.ai + Polygon.io collaboration or merger (High likelihood, High severity)**
If Polygon builds or acquires an MCP server for their full data suite (OHLCV + options + news) and FinancialDatasets.ai adds that data, you get "Polygon's data via MCP" — which undercuts Ithaca's data layer. Polygon has the engineering resources and developer distribution to do this in 6–12 months. Severity: high, because it removes Ithaca's data-accessibility advantage for the developer audience.

**2. QuantConnect publishes MCP endpoints for LEAN (Medium-High likelihood, High severity)**
QuantConnect has ~250K users, a mature backtest engine, and engineering resources. If someone internally champions "LEAN via MCP," they could ship it in one quarter. This would give developers a backtest endpoint from a trusted platform. It doesn't include Ithaca's research tools or observability, but it's a credible counter. Timeline: 12–18 months. Severity: high for the backtest dimension.

**3. Unusual Whales ships an API/MCP tier with broader data (Medium likelihood, High severity)**
Unusual Whales already has a paid API. If they wrap it in MCP tools (congressional, options flow, dark pool) with a clean developer interface, they become a real competitor for the alt data / flow data dimension. Their community moat means early adoption would be fast. Timeline: 6–12 months is plausible. Severity: high for congressional/insider/options-flow use cases.

**4. A large player (Perplexity, OpenAI, Anthropic) builds a financial MCP server (Low-Medium likelihood, Very High severity)**
If Perplexity builds a financial MCP tool suite with licensed data, or if OpenAI's operator ecosystem includes a financial data MCP server, the distribution advantage would be insurmountable for an early-stage Ithaca. Probability is moderate (financial data is a natural adjacent product for AI platforms). Severity is existential for the data-layer portion of the business.

**5. Regulatory risk on AI trading automation (Low likelihood, Moderate severity)**
If regulators issue guidance that AI-proposed trades require specific oversight mechanisms that Ithaca doesn't implement, it could block the deploy pathway. Ithaca's human-gated design is a hedge against this, but the specific regulatory requirements are unknown. Probability is low in the next 12 months but rising.

---

## Data Gaps

Specific financial data Ithaca is currently missing that competitors have:

| Data Type | Who Has It | Gap Severity |
|---|---|---|
| Real-time OPRA options flow (sub-second) | Unusual Whales, Bloomberg | High — current options data is likely delayed/downstream |
| Dark pool / block print data | Unusual Whales | Medium — specific to flow traders |
| Satellite / geospatial alt data | Quiver Quantitative | Medium — differentiating alt signal |
| Government contract / lobbying data | Quiver Quantitative | Medium — political economy signals |
| Licensed broker research reports | AlphaSense | High for institutional use cases |
| Earnings call transcripts (structured, searchable) | AlphaSense, Bloomberg | Medium — SEC filings are public but NLP isn't done |
| Tick-level historical trade data | QuantConnect, Bloomberg | High for serious backtest accuracy |
| Options chain historical (minute-level) | QuantConnect, Bloomberg | High for options strategy backtesting |
| Global equities small-cap fundamentals | Tikr, Bloomberg | Medium — current coverage skews large-cap US |
| Mutual fund / ETF holdings (full universe) | YCharts, Morningstar | Medium — we have ETF holdings but coverage may be partial |
| FX / rates / commodities real-time | Bloomberg, Polygon | High if macro strategies are in scope |
| Point-in-time index constituents | Bloomberg, QuantConnect | High for backtest survivorship bias correction |

The most critical gaps for Ithaca's core use case: real-time OPRA options data, tick-level historical data, and point-in-time index constituents (for correct backtesting).

---

## The Nightmare Scenario

**The nightmare scenario is: Anthropic or OpenAI builds a financial MCP server.**

Specifically: Anthropic publishes `mcp-server-finance` — a first-party MCP server with licensed fundamentals, news, and price data — as part of the Claude ecosystem. Or OpenAI builds financial data tools into their operator ecosystem.

Why this is existential:
1. **Distribution** — Claude has millions of users. A first-party financial MCP server gets immediate adoption from every Claude user building financial agents. Ithaca can't compete on distribution.
2. **Trust** — developers trust Anthropic/OpenAI infrastructure by default. A first-party financial server carries implicit trust that a third-party Ithaca has to earn.
3. **Cost** — if Anthropic cross-subsidizes the financial server (running it at cost or free to drive Claude adoption), Ithaca's pricing model breaks.

**The mitigation:** Ithaca must become more than a data layer before this happens. The defensible position is the full workflow (backtest + deploy + human-gated money path + observability), not the data access alone. A first-party MCP financial data server doesn't backtest, doesn't paper-trade, doesn't have a promote workflow. The "trust layer for AI money management" is harder to replicate than the data layer. Ithaca needs to be known for the workflow, not just the tools.

The secondary nightmare: Alpaca + QuantConnect announce a partnership and ship an MCP surface together — QuantConnect's backtest engine + Alpaca's execution + a shared MCP tool layer. This doesn't require a hyperscaler and is probably achievable in 12 months by two motivated engineering teams. It would directly replicate Ithaca's research-to-deploy-to-execute arc, minus the alt data depth and observability.

---

*End of competitive analysis. Next review recommended: Q4 2026 or when a Tier 1/2 competitor ships MCP tooling.*
