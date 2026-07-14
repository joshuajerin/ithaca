# Red-team critique: feasibility

I now have strong ground-truth. The engine is genuinely pure and portable (good), but the data layer has no real PIT vintaging, and the docs' central "Data Gateway makes PIT a property of the data plane" claim is far harder than implied. I have enough to write the red-team assessment.

I have enough ground truth. Here is the red-team assessment.

---

# Ithaca v2 — Build Feasibility & Sequencing Red-Team

I verified the load-bearing claims against v1 source before writing this. Findings, ranked by risk.

## What the docs get right (so I'm not just dunking)
- The engine **is** genuinely pure and portable: `engine/backtest.py:run_backtest` is `# Pure: no I/O. The caller owns fetching`; `engine/optimize.py` is "no DB / network / scipy ... trivially unit-testable." ~5,000 LOC of numpy that ports nearly verbatim. The "port the crown jewels" plan is sound and low-risk.
- Killing in-process codegen and making strategies declarative is the correct, non-negotiable call.
- `state.py` really does have the `SELECT ... FOR UPDATE` pattern (verified lines 151-162), so generalizing it is grounded.

Now the problems.

---

## Issue 1 — [CRITICAL] Point-in-time correctness is asserted, not achievable, with v1's data sources. The whole backtest value prop rests on this.

The Deploy doc claims PIT is "a **property of the data plane**" — the Data Gateway takes `asOf` and "returns only data that was knowable at asOf." **The underlying v1 sources cannot deliver this, and the docs never confront it:**

- `sources/prices.py` is Yahoo's live chart endpoint. Yahoo serves **survivorship-biased, dividend/split-restated** series with no vintaging. You cannot ask Yahoo "what did this close look like as known on date X." Truncating bars at `asOf` (which the doc proposes) does **not** fix restatement or survivorship — a delisted name simply isn't in the response *today*, so it's silently absent from any "historical" universe. This is the exact v1 survivorship lesson the docs claim to honor, re-introduced.
- `sources/fundamentals.py:fetch_fundamentals` returns **only a current snapshot** (`trailingPE`, `trailingEps` — today's values). `fetch_fundamentals_history` literally **estimates** the knowable-date as "period end + a conservative 45-day reporting lag" (verified, line ~125). That is a guess, not a filing date. A factor backtest on value/quality over this data has look-ahead baked into the *source*, and no gateway `asOf` parameter can remove bias the source never recorded.
- News (`publishedAt` from RSS `pubDate`) and EDGAR (`filingDate`) **do** carry real knowable-dates and are PIT-capable. So PIT correctness is *per-source*, not a uniform plane property.

**Resolution:** Demote the claim. PIT is a per-source *capability flag* surfaced in provenance (`pit: true|false|estimated`), not a guarantee the gateway can enforce. For v2.0, scope backtests to **price-only / technical strategies** (momentum, MA-cross, vol) where Yahoo's restated-but-consistent daily closes are defensible, and **explicitly forbid fundamental-factor backtests** until you have a vintaged fundamentals source (paid: Sharadar, Compustat PIT). Otherwise you ship a backtester whose headline use case is quietly wrong — the single worst possible outcome for a "financial tool-platform."

## Issue 2 — [CRITICAL] DOKS + per-job microVM sandbox + NetworkPolicy egress-deny + cluster-autoscaler is a massive infra project mis-sequenced as early/mid-phase.

The security and deploy docs casually require: gVisor/Kata or microVMs, seccomp profiles, cgroups v2, default-deny `NetworkPolicy` with a single allow to the Data Gateway, scale-to-zero autoscaling, a market-calendar-aware custom scheduler, and RLS migrations. That is **weeks-to-months of platform engineering** by someone who has run DOKS in anger. Meanwhile:

- The repo-sequencing doc puts the first DO run at **Phase 3** and has *no team-size or staffing* stated. WS-E ("Infra") is one parallel workstream expected to have "DO ready when the runner is."
- gVisor on DOKS is not a managed offering — you're installing and maintaining a runtime class on your nodes. Kata needs nested virt / bare-metal-ish nodes DO may not give you on standard droplets. **This is unvalidated.** Nobody confirmed gVisor runs on DO's managed nodes.

The deeper contradiction: the docs **also** say strategies are purely declarative (no agent code runs). **If specs are declarative and executed by your own trusted graph evaluator, you do not need a syscall-filtering microVM at launch.** The microVM is justified only by the *deferred* `CustomPythonNode`. The security doc itself says CustomPythonNode is "off by default, never shipped at launch" — yet it builds the entire heavyweight sandbox for it anyway.

**Resolution:** For v2.0, since no untrusted code runs, the runtime is *your own trusted code over validated data*. A plain container with cgroup limits + `activeDeadlineSeconds` + a default-deny egress NetworkPolicy is sufficient and is a fraction of the work. **Defer gVisor/Kata/seccomp to the phase that actually ships CustomPythonNode** — and gate that phase on a spike that proves the sandbox runtime works on DO. Don't build a microVM fleet to run numpy you wrote.

## Issue 3 — [HIGH] The "thinnest first slice" in the repo doc is wrong — it front-loads the spine but defers the riskiest unknowns.

Phase 1 ("two tools, agent calls them in-process, no DO") is a genuinely good thin slice and I'd keep it. But the phasing buries the three things most likely to kill the project until Phase 3-4:
- DO orchestration (Issue 2),
- PIT data correctness (Issue 1),
- real-time external-agent trace capture fidelity (Issue 5).

Classic critical-path inversion: the easy, already-proven work (porting pure numpy) is sequenced first; the unvalidated infra and the unsolved correctness problem are sequenced last, after sunk cost.

**Resolution:** Insert a **Phase 0.5 = three de-risking spikes, run in parallel with the Phase-0 skeleton, before committing to the phase plan:** (a) prove gVisor/egress-NetworkPolicy/scale-to-zero works on a throwaway DOKS cluster; (b) prove you can produce *one* defensibly-PIT backtest and enumerate which sources support it; (c) prove MCP trace capture survives a real Claude/GPT host (Issue 5). If any spike fails, the phase plan changes. Thin credible first *shippable* slice = Phase 1 + Phase 2 (agent calls tools in-process, UI renders the trace) with **no DO and no deploy layer at all** — that already demonstrates the core vision and defers every hard infra question.

## Issue 4 — [HIGH] Polyglot split (Python data-MCP + **TypeScript** control-plane) contradicts the architecture doc and re-introduces the backtest≠live divergence risk.

The repo-sequencing doc puts the control plane in **TypeScript**, while the system-architecture and deploy docs put it in **Python/FastAPI**. These are different designs presented as one. The TS choice is the worse one here:
- The control plane owns spec validation, the risk pre-attestation, and the lifecycle state machine. The risk attestation (`sum|w|` gross re-check) is the *exact v1 optimizer bug* and lives in numpy. Putting the control plane in TS means either re-implementing risk math in TS (a new divergence-bug class — the thing the docs explicitly try to kill) or an extra Python hop for every validation.
- It also splits the shared `core.run_tool` seam the architecture doc relies on (one shared Python core behind both MCP and REST). You can't share a Python core if the gateway is TS.

**Resolution:** Pick one. Given the crown jewels and the validator are Python, **the control plane is Python/FastAPI** (as topology + deploy docs say). The repo-sequencing doc's TS control plane should be overruled. Keep TS only for the web UI.

## Issue 5 — [HIGH] "Capture the agent's reasoning" is structurally limited and the UI over-promises it.

The honest core (MCP wire = trace) is correct and achievable: you own the server, so every `tools.call` is observable for free. But:
- The "REASONING rail" depends on `emit_reasoning` / MCP notifications that **a BYO agent will almost never call.** Claude Desktop, GPT, and custom hosts do not volunteer chain-of-thought to an MCP server. The realistic default is an **empty left column** — the centerpiece three-column UI degrades to two.
- The `X-Ithaca-Run` header / `session_id` correlation assumes the agent host forwards a stable session across reconnects. Many MCP hosts open a fresh transport per tool call or per task; you may get fragmented sessions you can't stitch into "one unbroken research→proposal→backtest chain." This is unproven against real hosts.
- The "inferred/templated annotations" fallback is reasonable but the docs sell it as a minor footnote when it'll be the *primary* content.

**Resolution:** Design the UI **reasoning-optional-first**: the tool-call timeline + evidence panels must be the compelling product with zero reasoning. Make the reasoning rail an opt-in enhancement, not the headline. Run the Phase-0.5 spike (Issue 3c) against ≥2 real agent hosts to learn what session/reasoning fidelity you actually get *before* designing IA around it.

## Issue 6 — [HIGH] Postgres LISTEN/NOTIFY as the launch event bus + SSE replay will not carry the trace + telemetry load and has a hard payload limit.

The topology doc launches the event bus on Postgres LISTEN/NOTIFY ("transactional, gap-free, one fewer moving part") and replays SSE from Postgres. Real constraints the doc ignores:
- NOTIFY payloads are capped at **8000 bytes**; trace payloads (tool args + result summaries + provenance) will exceed this, forcing a notify-then-SELECT pattern that adds DB read load per event.
- Every SSE reconnect replaying `from_seq` is a Postgres scan; with paper-live ticks + backtest progress + per-tool-call events fanning to multiple UI tabs, the system-of-record DB becomes the hot path for streaming. This is a known scaling cliff, not a "scale later" tweak.

**Resolution:** Fine for Phase 1-2 demos. But don't call it the launch bus uncritically — set a concrete threshold (events/sec, concurrent SSE clients) at which you move trace fan-out to Redis Streams, and write the `(run_id, seq)` consumer against an interface from day one so the swap is config, not rewrite. Keep money-path events transactional in PG; move *observability* fan-out off PG early.

## Issue 7 — [MEDIUM-HIGH] Two parallel, slightly-different security/spec models across docs = the seam where v1's "tested path ≠ shipped path" bug recurs.

The deploy doc's `StrategySpec` is a **signal-graph DAG of operators**. The security doc's strategy is a `{signal → construction → constraints → schedule}` **declarative graph** with a separate "scripted escape hatch." The data-layer doc has `backtest.run` as a research primitive over `engine/strategies.py` (which are `(closes, params) -> positions` functions, **not** a DAG). Three different mental models of "what a strategy is."

If the agent-facing `propose_strategy` schema, the validator, and the executor are built from different docs, the validated artifact and the executed artifact diverge — exactly v1's failure theme.

**Resolution:** One canonical `StrategySpec` schema in `packages/contracts`, authored once, with **one** validator and **one** evaluator consuming it. Decide now whether v2.0 strategies are (a) the existing parameterized `engine/strategies.py` primitives (far simpler, ships faster, covers MA-cross/momentum) or (b) the full operator-DAG (more expressive, much more validation surface). I'd ship (a) for v2.0 and defer the DAG; the DAG's semantic linter (cycle detection, feasibility pre-attestation, registry) is real work for marginal launch value.

## Issue 8 — [MEDIUM-HIGH] Risk pre-attestation "infeasibility" check is presented as easy; it's the v1 bug class and needs to be a hard, tested gate, not a lint.

The deploy doc's example — reject `top:2, longOnly, gross 1.0, maxNamePct 0.25` as statically infeasible — is correct in spirit but the *general* feasibility check across construction scheme × constraints × optimizer projection is nontrivial (it's why v1 shipped a 311%-gross book). Static config-level checks catch only the trivial cases; the real bug was the **projection** ending on net+box instead of gross-L1 (confirmed in `optimize.py` — `gross_limit()` floors gross at `|net|` but the projection order is the issue).

**Resolution:** The gross-L1 re-check must run **post-projection, in the executor, on every emitted target book**, refusing to emit a breaching book — not just a design-time lint on the spec. Make it a gating CI test with the v1 311%-gross case as a fixture. Treat the design-time lint as a nicety, the runtime attestation as the boundary.

## Issue 9 — [MEDIUM] IEX DEEP order-book reconstruction is correctly flagged as huge but still under-scoped as a launch tool.

Verified: `iex_deep.py` confirms "a single DEEP day is ~13 GB gzipped" and streams/decodes incrementally — the parsing is real and good. But exposing `market.reconstruct_order_book` as an MCP tool means a single agent call can pull and decode 13GB on your infra, on demand, per tenant. The data-layer doc's own open question #3 admits this. Per-call deadlines don't bound bytes; the v1 lesson was specifically the *unbounded byte stream*, not just time.

**Resolution:** Cut from v2.0 agent surface. If kept, it must be: explicit high-cost class, a hard **byte cap** (not just wall-clock), async job (not a synchronous tool call), and pre-materialized/cached per session date. Don't let an agent trigger 13GB of decode on a synchronous MCP call.

## Issue 10 — [MEDIUM] "Stale-while-revalidate keeps serving stale when breaker open" can serve unboundedly stale data to a money-adjacent path with only a flag to warn.

The data doc makes stale-serve honest via provenance (good). But paper-live re-evaluates signals on "REAL current market data via the Data Gateway." If the breaker is open and the gateway serves a stale quote labeled `freshness:stale`, the paper-live runtime may **trade on stale marks** unless it explicitly refuses stale on the execution path. Provenance honesty protects the *agent's reasoning*; it does not protect the *fill engine* unless someone wired a freshness floor into the tick.

**Resolution:** The paper-live tick must declare a max-staleness tolerance and **skip-and-alert** (the doc's own pattern for lost ticks) when data exceeds it, rather than fill on stale marks. Make freshness a hard precondition on the money path, distinct from the soft display label on the research path.

## Issue 11 — [MEDIUM] OAuth 2.1 + device-code + 15-min token minting + edge WAF + hash-chained tamper-evident audit is a lot of security surface for v2.0; some is gold-plating.

The security doc is excellent but maximalist. Hash-chained per-tenant audit streams, ASN reputation WAF, MFA/TOTP, device-code linking, and short-lived token exchange are all defensible *eventually*. For a paper-only launch with no real money and a handful of pilot tenants, building all of it pre-launch competes for the same scarce eng time as the actually-hard infra (Issue 2).

**Resolution:** v2.0 minimum: hashed API keys (already a v1 pattern), the RLS invariant + the CI test that fails on any unscoped table (this is the high-value one — keep it), per-principal rate limits, and append-only audit. **Defer** OAuth device-code, token exchange, hash-chaining, and WAF to post-pilot. Keep `deploy:live` unissuable (cheap, high value — keep).

## Issue 12 — [MEDIUM] RLS "cannot be forgotten" is overstated; it has real operational sharp edges the docs don't budget for.

RLS as the tenancy backstop is the right call, but the docs treat `SET LOCAL app.tenant_id` as free. Reality: it requires every connection to run as a non-superuser non-owner role (migrations/owner bypass RLS — a footgun), connection-pooler (PgBouncer transaction mode) interactions with `SET LOCAL`, and a discipline that the *worker* and *Data Gateway* connections also set the GUC. The cross-tenant escape hatch (`list_all_*`) is exactly where it'll be forgotten. The "global upstream cache" exception (data doc §4.2) also lives outside RLS and needs its own audited boundary.

**Resolution:** Keep RLS, but budget for the operational work: pooler config, a non-owner app role, and a test that the *pooled* path (not just a raw connection) enforces isolation. Make the global-cache boundary a single reviewed module, not an ad-hoc exception per call site.

---

## Bottom line — what to actually do for v2.0

1. **Ship Phase 1 + 2 only as the credible first release** (agent calls in-process tools; UI renders the trace + a price-only backtest). No DO, no deploy layer, no sandbox. This proves the entire vision and defers every hard problem.
2. **Run three de-risking spikes (Issue 3) in parallel before committing the rest of the phase plan:** DO sandbox/egress/autoscale viability, one defensible PIT backtest, real-host trace fidelity.
3. **Cut from v2.0:** fundamental-factor backtests (Issue 1), the operator-DAG spec in favor of parameterized v1 strategies (Issue 7), the microVM sandbox until CustomPythonNode actually ships (Issue 2), IEX DEEP as an agent tool (Issue 9), and the OAuth/WAF/hash-chain security tier (Issue 11).
4. **Resolve the two design contradictions now:** control plane language (Python, Issue 4) and the single canonical StrategySpec (Issue 7).
5. **Keep as load-bearing and non-negotiable:** declarative-only / no in-process eval, the RLS invariant + its CI test, the post-projection gross-L1 attestation as a *runtime gate* (Issue 8), aggregate deadlines, and `deploy:live` unissuable.

The single biggest honesty gap: **the docs sell point-in-time-correct backtesting as an infra property when the free data sources can't support it.** Fix that framing before anyone builds the Data Gateway, or you ship a backtester that lies.