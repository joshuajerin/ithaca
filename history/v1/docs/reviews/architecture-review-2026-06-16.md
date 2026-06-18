# Doomberg Architecture Review — 2026-06-16

> Multi-agent flaw-finding + feature review. 78 agents, 8 dimensions, **59 verified findings**
> (each adversarially verified against the real code before inclusion). Dimensions: orchestrator,
> security/tenancy, data sources, quant engine, state/scalability, frontend, testing/CI, self-building codegen.

## 1. Executive summary

Doomberg's architecture is functionally rich but carries a small number of severe, exploitable defects
concentrated in its most novel surface — runtime AI code generation. Two **critical** in-process RCE paths
exist: the static AST guard for generated Python is trivially bypassed via string-hidden dunder walks, and
the validation sandbox does not cover the in-process `exec_module`/`build()` that actually runs generated
code. Beyond codegen, the platform has real multi-tenant isolation gaps (template store and in-memory
dashboards leak across firms), money-path concurrency bugs (unlocked read-modify-write on strategy books, an
optimizer that violates hard gross-exposure limits), and effectively no CI gate (3 of 33 test suites run, and
the core LLM→panel path is untested). Biggest risks in order: contain generated-code execution, close
cross-tenant data access, then harden the orchestrator's deadline/heartbeat behavior and the money-path
concurrency. Most findings are well-isolated and fixable without architectural rewrites; the codegen
sandboxing is the one item requiring a structural change (out-of-process execution).

## 2. Top risks ranked

### Critical

- **AST guard bypassable → in-process RCE.** code_guard auditor only inspects dunders as AST nodes;
  string-literal attribute paths (`string.Formatter().get_field("0.__globals__[__builtins__][__import__]", ...)`)
  reach a live `__import__` and `os.popen`. `code_guard.py:117-129`. **Fix:** stop treating the static guard as
  a security boundary; execute all generated code out-of-process (stripped `__builtins__`, network-denied,
  rlimited), drop `string` from the import allowlist, scan string literals for dunder/reflection tokens.

- **Validation sandbox doesn't cover execution.** `_validate_python` runs candidates in an isolated subprocess,
  but `stream_feature_request` then `exec_module`s the file in the main server process and invokes `build()`
  in-process per request. `feature_builder.py:283-322` / `dynamic_skills.py:63` / `harness.py:81`. **Fix:** make
  the subprocess the *execution* environment for the builder's whole lifetime; marshal only validated JSON back.
  Never `exec_module` generated code in the API process.

### High

- **Client-side panel guard is a substring denylist, then `new Function`-eval'd in every browser.**
  `globalThis["fe"+"tch"]` / `["local"+"Storage"]` evade `_TSX_BANNED`; the TSX runs in the page's main realm
  with full access to cookies/fetch/storage. `feature_builder.py:327-351` (+ `registry.ts:83-84`). **Fix:**
  sandboxed cross-origin iframe (no `allow-same-origin`) via postMessage, or a declarative non-executable schema.
- **Generated skills are global across tenants; kill-switch doesn't isolate or unload.** `register_module`
  writes process-global `SKILLS[pt]` with no firm key; dispatch/startup unscoped; `require_codegen_enabled` only
  gates the build endpoint. `dynamic_skills.py:96-97`. **Fix:** key generated skills by firm_id at registration
  and dispatch, filter `get_definitions()`/`run_skill` by caller, unregister on disable.
- **Cross-firm IDOR: in-memory `get_dashboard` ignores firm scoping.** Raw `_mem.get(id)` lets any firm restore
  another's dashboard by guessing a 12-hex id (reachable whenever `DATABASE_URL` is unset).
  `dashboard_store.py:138-140`. **Fix:** add the `(rec.firmId or DEFAULT_FIRM_ID) == fid` guard.
- **Strategy templates have no tenant scoping.** `template_store` omits `firm_id`, never imports `tenant`;
  `delete_template` only checks `id.startswith('user-')` — cross-firm read, clone, destructive delete.
  `template_store.py:25-30`. **Fix:** add `firm_id` column+index, stamp from `tenant.resolve_firm()`, filter all.
- **Strategy book updates are unlocked read-modify-write (lost-update on the money path).** `strategy_store.upsert`
  does `INSERT ... ON CONFLICT DO UPDATE` over a full prior read with no row lock; worker advisory lock guards
  worker-vs-worker but not worker-vs-API / API-vs-API. `strategy_store.py:184-211`, `strategy.py:253-273`.
  **Fix:** `SELECT ... FOR UPDATE` in one txn (mirror `state.py:_mutate`) or optimistic version guard.
- **Optimizer violates the gross (L1) exposure limit on the final projection.** `_project_feasible` ends with
  `_project_box_sum` (net + box, NOT gross L1), so a "gross 200%" book returns as `optimal` at ~311% gross
  (reproduced numerically). `optimize.py:177-188`. **Fix:** re-check `sum|w|` vs gross after final budget step;
  iterate Dykstra to tolerance or return `infeasible-relaxed`.
- **No aggregate deadline across chained LLM calls.** Voice build runs 3 serial `ai.chat` calls (relevance →
  orchestrate → narration), each 30s `max_retries=0`, ~90s worst case — past the ~60s proxy ceiling.
  `agent.py:1738-1790`. **Fix:** wall-clock deadline at start of `_orchestrate_build`, shrinking per-call timeouts,
  fall back to heuristics when budget spent.
- **Streaming build emits no SSE heartbeat during blocking LLM work.** Build branch is a single `yield {done}` —
  all chained calls run before the first byte; idle-timeout proxies kill it. `agent.py:1853-1854`. **Fix:** mirror
  the feature-builder pattern (worker thread + `: keepalive`).
- **Lifecycle keyword routing runs before intent classification.** `_handle_lifecycle` (regex) runs before
  `_classify_intent`, so "how do I retire a strategy?" matches `\bretire\b` and mutates persisted state.
  `agent.py:1801-1813`. **Fix:** classify first, or gate lifecycle on `intent != 'question'`.
- **Treasury and credit-spread fetches bypass the resilience wrapper.** `_fetch_treasury_year`,
  `_fetch_fred_latest`, `_fetch_fred_series` use raw `httpx.Client` — no retry/backoff/breaker; a transient
  503/429 nulls the whole curve. `sources/rates.py:91`. **Fix:** route through `_resilient.request` (mechanical).
- **IEX DEEP reconstruct has no wall-clock timeout on a ~13 GB stream.** Only per-read timeouts; a
  truncated/malformed capture drains the entire tail and ties up a worker thread. `sources/iex_deep.py:450`.
  **Fix:** deadline/byte-cap check inside the message loop.
- **No top-level React error boundary.** Only `PanelErrorBoundary` (generated panels). A render throw in
  `Terminal.tsx`/`Dashboard.tsx`/typed panels blanks the whole app. `App.tsx:43-56`. **Fix:** wrap `AuthGate`.
- **Typed panels render `panel.data as any` with no boundary.** `renderContent()` passes unvalidated data into
  panels calling e.g. `row.price.toFixed(2)`; one bad field throws during render. `PanelContainer.tsx:309-403`.
  **Fix:** per-panel boundary → existing "Data Acquisition Failed" fallback.
- **Only 3 of 33 test suites gate merges.** Just `smoke`, `panel-runtime-test`, `voice-backend` carry
  `isValidation`; auth/security/permissions/strategy/engine/rebalance/compliance/audit run nowhere. No
  `.github/workflows`, no `pytest.ini`. `.replit:31-62`. **Fix:** `isValidation` workflow running `pytest`.
- **Intent routing is a 1300-line, 197-branch keyword cascade where ordering is the spec.**
  `_orchestrate_heuristic` has 82 `return panels` exits; misplaced branch silently mis-routes.
  `agent.py:3383-4700`. **Fix:** registry of `(matcher, builder, priority)` + per-intent query tests; split file.

### Medium

- Lifecycle handler swallows real errors → generic build (`except Exception: return None`, no log). `agent.py:1641-1642`.
- No retry/backoff for transient LLM failures (`max_retries=0` + `except: pass`). `ai.py:53-60`.
- `compliance_store._mutate` unlocked read-modify-write on global config row. `compliance_store.py:211-264`.
- `session_state` first concurrent insert not serialized (`FOR UPDATE` locks nothing when no row). `state.py:140-186`.
- Session ownership recorded but never enforced (within-firm IDOR; `get_session_owner` unused). `state.py:219-238`.
- Registration/invite TOCTOU race + orphan firm; UNIQUE violation → 500 not 409. `main.py:260-273`, `auth_store.py:237-271`.
- DB pool starvation → silent in-memory divergence (PoolTimeout → `_mem` fallback). `db.py` / `state.py`.
- Append-only audit + `session_state` grow unbounded; expired `auth_sessions` cleaned lazily. `compliance_store.py:281-354`, `state.py:65-92`.
- Worker rebalance/snapshot: full-table load + N+1 `get_config` across all firms. `strategy_store.py:134-149`, `strategy.py:682-702`.
- `new Function` eval of AI panel source (bypassable blacklist, unsandboxed). `registry.ts:66-91`.
- Factor attribution mixes arithmetic factor returns w/ geometric realized return → mislabeled idiosyncratic. `engine/attribution.py:357-361`.
- Cross-sectional signal: union-calendar rebalance, forward returns in own bar index → misaligned windows. `engine/signals.py:342-387`.
- Streaming reader has no AbortController; superseded stream clobbers newer answer. `Terminal.tsx:265-330`.
- `_is_dunder`/auditor blind to f-strings + string-literal reflection tokens. `code_guard.py:82-83,117-120`.
- Large tables render every row, no virtualization, inside `layout` AnimatePresence → thrash. `ScreenerPanel.tsx:36-64`.
- No staleness floor / last-known-good when upstream down (flips to mock/empty). `cache.py:44`.
- EDGAR submissions parsing: positional flatten, only `filings.recent`, drops overflow + older Form 4/5. `sources/edgar.py:146`.
- Per-attempt/per-call `httpx.Client` construction defeats keep-alive. `sources/_resilient.py:185`.
- Core LLM tool-call→panel path untested (every test forces `ai_available=False`). `agent.py:1752-1763`.
- `panel-runtime-test` couples build + live server + LLM retries + live yfinance into one slow nondeterministic gate. `IntradayChartPanel.integration.test.tsx`.
- Load/perf regression gate defaults OFF (`LOAD_GATE_LATENCY=0`) and runs in no workflow. `scripts/loadtest_api.py:72-74`.

### Low (noted)

Question-path double LLM call no shared timeout (`agent.py:1809-1811`); internal exception text leaked in SSE/502
(`main.py:557-558`); CORS allow-list silently empty when Replit env unset (`security.py:48-64`); EDGAR global
spacing lock sleeps under the lock (`edgar.py:57`); Polymarket/Yahoo schema changes → indistinguishable empty
results (`polymarket.py:203`); Monte Carlo `var95` horizon-terminal, name-collides with daily (`montecarlo.py:112-113`);
`risk_contributions` docstring claims non-negative 0-100 decomp (`optimize.py:584-594`); unweighted mean
cross-sectional R² (`riskmodel.py:93-97`); mobile console input enabled during streaming (`Terminal.tsx:869`);
chat transcript uses array index as React key (`ChatPanel.tsx:206-239`); per-process `_schema_ready` DDL races
(multiple stores); `execute_many` unbatched single txn (`db.py:163-170`); untyped `GeneratedPanel` fallback
(`GeneratedPanel.tsx:51-64`); localStorage transcript accepts malformed `kind`/no corrupt-session recovery
(`useConsoleConversation.ts:28-51`); ChatPanel data hooks ignore loading/error + dead fetches (`ChatPanel.tsx:34-37`);
standalone suites lack consistent `sys.exit` (`test_engine.py:951-963`); DB tests fully monkeypatch `db`
(`test_datalayer.py:45-56`); smoke probe disables AI (`test_smoke.py:98-103`); post-merge runs installs but no
tests, 20s timeout (`scripts/post-merge.sh:1-4`); TSX artifact left registered if later write fails (`feature_builder.py:505-526`).

## 3. Cross-cutting themes

1. **Static-guard-then-trust is the dominant security failure mode** — both critical RCEs, the client-side panel
   guard, and the f-string gap all assume a denylist/AST audit can make untrusted LLM code safe to run in a
   privileged realm. One architectural decision → five findings.
2. **"Never crash" swallowing degrades silently and erases audit trails** — broad `except Exception: pass/return None`
   in the lifecycle handler, every LLM caller, the data-source fetchers, the state pool-timeout path. The module has
   no logging at all. Consequence: lost mutations, regex-only routing, mock-for-real swaps, per-instance divergence.
3. **Multi-tenant isolation is per-store, not an invariant** — correct in `strategy_store`/`dashboard_store` DB
   paths, missing in `template_store`, the in-memory `get_dashboard`, and the generated-skill registry; `user_id`
   scoping recorded but never enforced. Omissions invisible until exploited.
4. **Unlocked read-modify-write recurs on every mutable store** — strategy books, compliance config, first
   `session_state` insert. `state.py:_mutate` has the correct `FOR UPDATE` pattern the others fail to follow.
5. **Per-call timeouts exist but aggregate budgets don't** — orchestrator (90s), question path (60s), IEX
   reconstruct (unbounded) all exceed the ~60s proxy ceiling.
6. **Tests exist but don't gate, and the paths that ship aren't the paths tested** — 30 suites run nowhere;
   orchestrate tests force `ai_available=False`; smoke disables AI; DB tests stub all SQL; perf gate defaults off.

## 4. Prioritized remediation sequence

1. **Contain generated-code execution (Critical).** Move both `exec_module` and every `build()` into the isolated,
   network-denied, rlimited subprocess, returning only validated JSON. Neutralizes both critical RCEs; downgrades
   the AST/f-string gaps to defense-in-depth. The only remotely-exploitable path to full server compromise.
2. **Sandbox the client panel realm (High).** Cross-origin iframe (or declarative schema) + key generated skills by
   `firm_id`. Closes browser token exfiltration + cross-tenant skill execution.
3. **Close cross-tenant data access (High/Medium).** `firm_id` on `template_store`, firm guard on in-memory
   `get_dashboard`, enforce session ownership. Low effort, high blast radius, no architectural change.
4. **Protect the money path (High/Medium).** Fix the optimizer gross-exposure violation; convert
   strategy/compliance/session mutations to `FOR UPDATE` transactions.
5. **Stand up a real CI gate (High).** Wire `pytest artifacts/api-server/tests` into an `isValidation` workflow +
   add the LLM tool-call→panel test. Do this early so subsequent fixes can't silently regress.
6. **Harden orchestrator/data-source reliability (High/Medium).** Aggregate deadline + SSE heartbeat in
   `_orchestrate_build`, reorder lifecycle-vs-classify, route Treasury/FRED through `_resilient`, bound IEX reconstruct.
7. **Frontend resilience + remaining mediums.** Top-level + per-panel error boundaries, AbortController,
   virtualization, stale-serve cache tier, observability/logging cleanup. Parallel track.

---

# Feature & Reliability Roadmap

Grounded in the findings above. Everything extends systems that already exist.

## Reliability / trust features ("Can I believe the number?")

- **Data lineage & as-of provenance on every panel** — standard `{source, asOf, freshnessSec, mode: live|stale|mock, coverage}` block rendered as a badge. The cache already knows `asOf` (`cache.py:44`); surface it instead of discarding it. A stale-90s real treasury curve is tradeable; a silently-fabricated mock labeled identically is a trust-killer.
- **Stale-while-revalidate / last-known-good tier** — on producer exception/open circuit, serve last good value tagged `stale` with real `asOf` instead of mock/blank.
- **Confidence / coverage surfacing on quant panels** — `methodology` footnote: linking basis, horizon of each risk figure (rename Monte Carlo → `terminalVar95`), symbol coverage, flag when "Specific" exceeds an explained-variance threshold. (attribution.py:357, optimize.py:584, montecarlo.py:112, riskmodel.py:93)
- **Hard risk-limit attestation** — post-projection feasibility re-check; never return `optimal` when `sum|w| > gross + tol` (optimize.py:177).
- **Reproducibility / audit replay** — stamp every build with inputs to reproduce (query, sid, source asOf set, engine params, seed); "Reproduce this panel"; log every lifecycle action.
- **SLA / health & data-freshness panel** — per-source breaker state, last-good timestamps, LLM degraded-mode rate, pool saturation. Reuses `_resilient` breaker state + `pool_stats`.

## High-leverage NEW capabilities (extend what exists)

- **Deterministic + explainable routing** — decompose `_orchestrate_heuristic` into a `(matcher, builder, priority)` registry + representative-query tests; surface "I interpreted this as X because Y".
- **Strategy lifecycle as first-class guarded workflow** — classify before lifecycle, gate on question-signal, explicit confirmed action panel with criteria/stage/diff preview.
- **Backtest / signal integrity mode** — "rigor" toggle: common aligned calendar, non-overlapping forward windows, Carino-linked attribution (already in `brinson_linked`, wire into `factor_attribution`), "methodology integrity" badge.
- **Sandboxed self-built panels as a real product** — only after out-of-process exec + iframe + firm_id keying; then "describe a panel and the terminal builds it" is sellable, not a liability.
- **Per-user working state & sharing** — enforce ownership (403 on userId mismatch), then add intentional, audited sharing of DCF models/watchlists/dashboards.
- **App-shell resilience** — per-panel + app-shell error boundaries so one bad panel downgrades a tile, not the session.

## Quick wins vs big bets

**Quick wins (days):** classify-before-lifecycle; gross re-check → `infeasible-relaxed`; rename `var95`→`terminalVar95`;
React error boundaries; firm-scope in-memory `get_dashboard`; `firm_id` on templates; shared deadline + SSE heartbeat;
one jittered LLM retry; provenance/`asOf` badge; wire full pytest + load gate into CI.

**Big bets (weeks):** out-of-process + iframe-sandboxed self-building skills; intent registry replacing the 197-branch
heuristic; stale-while-revalidate + full resilience coverage; quant integrity mode; per-user state enforcement +
sharing; atomic strategy-mutation path.

**Sequencing:** the two self-building critical RCEs and the gross-exposure / lifecycle-mutation correctness bugs gate
trust for any professional rollout — do them first even though some are "big bets." The provenance badge, error
boundaries, and CI wiring are cheap force-multipliers that make every subsequent change safer to ship.
