# Design: Security, Multi-tenancy, Compliance & Sandboxing

I now have enough grounding in v1's actual mechanisms (contextvar tenant scoping that was applied per-store rather than as an invariant, the FOR UPDATE pattern in state.py, the cookie/PBKDF2 auth, the role matrix, the in-process exec RCE). I have everything I need to write the v2 design doc. The task explicitly says to return findings as the final message, not write a file.

Let me produce the design doc as my final output.

---

# Ithaca v2 — Security, Multi-Tenancy & Safe-Execution Design

**Scope:** the cross-cutting trust layer for the v2 tool-platform. Designed explicitly *away* from the five systemic failure modes verified in the v1 review (`/Users/joshuajerin/Desktop/jarvis/ithaca/docs/reviews/architecture-review-2026-06-16.md`): static-guard-then-trust, per-call-site tenancy, unlocked read-modify-write, per-call-but-no-aggregate timeouts, and tests-that-don't-gate.

**Threat model (who we defend against):**
- T1 — A malicious or compromised **BYO agent** (it authenticates legitimately, then tries to read another tenant's data, exfiltrate secrets, or escape the strategy sandbox).
- T2 — A **malicious strategy/algorithm author** (the strategy code itself is the attacker — RCE, network egress, resource exhaustion, lateral movement to the control plane). This is the v1 RCE class, now first-class.
- T3 — A **confused-deputy** in our own code (an unscoped query, a forgotten tenant filter — v1's #1 systemic flaw).
- T4 — **External abuse / DoS** on the public MCP surface (credential stuffing, request floods, slow-loris, expensive-tool amplification).
- T5 — **Accidental real-money execution** ("paper" silently reaching a real broker).

---

## 1. Identity & Auth

### 1.1 The account model (three distinct objects, never conflated)

```
Tenant (org/firm)                 ← the isolation boundary. Owns everything.
  ├── User (human)                ← logs into the web UI. Has a role.
  ├── Agent (logical principal)   ← a registered BYO agent ("my Claude trader")
  │     └── Credential (secret)   ← an API key OR OAuth client; scoped; revocable
  └── all data rows / deploy jobs / artifacts  ← carry tenant_id (see §2)
```

Key rule: **a Credential is never the principal — the Agent is.** A credential is a rotatable secret *belonging to* an agent. Revoking/rotating a credential never changes the agent's identity, its deployed strategies, or its audit history. This is what makes key rotation safe and lets us attribute every action to a stable principal.

### 1.2 How the BYO agent authenticates to the MCP server

Two supported flows, both resolving to the same `AgentPrincipal`:

1. **API keys (primary, the 80% path).** Format: `ith_<env>_<keyid>_<secret>` (e.g. `ith_live_k7f3_…`). We store only `sha256(secret)` plus a non-secret `keyid` lookup column — mirroring v1's session-token discipline (`auth.py` stores only `hash_token`). Constant-time compare. The visible prefix lets us scan-and-revoke leaked keys and lets the user identify a key in the UI without exposing it. Keys are shown **once** at creation.
   - **Why primary:** agents run headless; the device-code dance is friction for a long-lived daemon.
2. **OAuth 2.1 client-credentials (for org/programmatic issuance) + device-code (for interactive first-link).** A user "links an agent" in the UI via device-code (agent prints a code, user approves in the web UI under their authenticated session). This binds the agent to the tenant *with the user's explicit consent and role*, then issues a client-credentials pair the agent uses thereafter. This is the clean path for "connect my Claude/GPT/custom agent."

Both flows yield short-lived **bearer access tokens** (15 min) for the MCP session; the long-lived secret (API key / client secret) is only used to mint them. This bounds the blast radius of a leaked in-flight token.

> v1 lesson applied: v1 had no machine-principal model at all (only human cookies, `auth.py`). v2 makes the agent a first-class, separately-credentialed principal so we can scope and rate-limit it independently of any human.

### 1.3 How the web UI user authenticates

Keep v1's proven mechanism, hardened: httpOnly, `Secure`, `SameSite=Lax` session cookie; opaque random token, only `sha256` stored (`auth.py:hash_token`); PBKDF2-HMAC-SHA256 at ≥200k iterations for passwords. **Add:** server-side session records with absolute + idle expiry, explicit logout-all, and a `csrf` double-submit token for state-changing cookie-authed endpoints (v1's CSP was strict but it had no CSRF token; `security.py`). MFA (TOTP) for `admin` role.

### 1.4 Scopes & permissions per credential

Authorization is **role (human) ∩ scope (credential) ∩ tenant**. Both ceilings apply; the effective permission is the intersection.

- **Human role** — keep v1's ranked matrix (`permissions.py`: `read-only < analyst < trader < admin`, fail-closed on unknown action). It still governs UI users.
- **Agent credential scopes** — a separate, finer, *capability* axis stamped on each credential. An agent credential can never exceed the role of the user who linked it, and is *further* narrowed by its scopes:

| Scope | Grants |
|---|---|
| `data:read` | call DATA-LAYER tools (news, ticks, fundamentals, factor models, backtest primitives) |
| `strategy:author` | create/update strategy definitions (not deploy) |
| `deploy:backtest` | submit backtest jobs |
| `deploy:paper` | deploy to the live paper runtime |
| `deploy:live` | **reserved, not issuable at launch** (paper-only, §4.3) |
| `account:read` | read own tenant's positions/trades/audit |

A read-only data agent gets `data:read` only — even if linked by an admin. **Deny-by-default, fail-closed** (v1 `permissions.can()` already does this; we keep that exact discipline and extend it to scopes). Scope checks live in the single auth gate, not at call sites (§2).

---

## 2. Multi-tenancy as a HARD INVARIANT

This is v1's #1 systemic flaw (review §3.3: "isolation is per-store, not an invariant" — correct in `strategy_store`/`dashboard_store`, *missing* in `template_store`, in-memory `get_dashboard`, and the generated-skill registry). v1's `tenant.py` contextvar was the right idea but it was **advisory**: each store had to *remember* to call `tenant.current_firm_id()` and filter, and the ones that forgot leaked. We make forgetting structurally impossible.

### 2.1 Defense layer A — Postgres Row-Level Security (the backstop that cannot be forgotten)

Every tenant-owned table gets a non-null `tenant_id` and an RLS policy. The application connects as a **non-superuser role that has RLS forced** and sets `SET LOCAL app.tenant_id = $1` at the start of every transaction from the resolved principal.

```sql
ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategies FORCE ROW LEVEL SECURITY;   -- applies even to table owner
CREATE POLICY tenant_isolation ON strategies
  USING      (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

The critical property: **a query that forgets its tenant filter returns zero rows, not another tenant's rows.** A forgotten filter on a write fails the `WITH CHECK`. This is the structural fix for the v1 IDOR class (`get_dashboard`, `template_store`) — the database enforces it even when the application code is wrong. `current_setting('app.tenant_id')` with no value set → error → fail closed. This is the single most important change from v1: *isolation moves below the application code, where it cannot be omitted per-call-site.*

### 2.2 Defense layer B — a scoped data-access layer that makes unscoped queries un-writable

RLS is the backstop; we *also* remove the footgun at the application layer so unscoped queries are not merely caught but un-expressible:

- There is **no** raw `db.execute(sql)` available to feature/store code. The DB module exposes only a `TenantSession` obtained from the request/job context: `session = ctx.db()`. `TenantSession` opens the transaction, runs `SET LOCAL app.tenant_id`, and is the *only* way to get a cursor.
- Every ORM model for a tenant table inherits from `TenantScoped`, which carries `tenant_id` and whose default manager is bound to the session's tenant. There is no "unscoped" manager exported.
- A unit/CI test (gated — see §5.4 and the v1 "tests don't gate" lesson) enumerates every table; any tenant-eligible table **without** an RLS policy and a `tenant_id` NOT NULL column **fails the build**. New tables are isolated by default or they don't merge. This converts "remember to scope" into "the schema is wrong and CI is red."

### 2.3 Tenant resolution = the auth gate, set once, never threaded

Keep v1's contextvar ergonomics (`tenant.py` — clean, avoids threading `firm_id` through deep call sites) but bind it to the verified principal in a single middleware/dependency, and make every downstream `TenantSession`/job read it. The background worker and deploy runtime enter `firm_context()` per item exactly as v1's worker did — but now if they forget, RLS denies them rather than leaking. The contextvar becomes a *convenience*; RLS is the *guarantee*.

### 2.4 Non-DB artifacts carry the tenant key too

Deploy jobs, backtest result blobs, log streams, and strategy artifacts are **object-store paths prefixed `tenant/<tenant_id>/…`** with bucket IAM policies scoped per prefix, and a `tenant_id` column on the job row (RLS-protected). The runtime sandbox (§3) is handed *only* its own tenant's scoped, short-lived credentials — it physically cannot address another tenant's prefix. v1's in-memory `_mem` dicts that bypassed firm scoping (`dashboard_store`, generated-skill `SKILLS[pt]`) are eliminated: there is no process-global, un-keyed store anywhere in v2.

---

## 3. Safe Strategy Execution (the highest-risk surface)

This is the v1 two-critical-RCE class, made first-class. **Non-negotiable architectural rule: no in-process `eval`/`exec`/`exec_module`/import of agent- or user-authored code, ever, anywhere.** v1's both criticals came from running generated code in the API process behind a static AST guard (`code_guard.py`, `dynamic_skills.py`); v1's *own* review concluded "stop treating the static guard as a security boundary." We adopt that as law: **static analysis is lint, not a boundary.** We also DROP v1's runtime AI-codegen path entirely (per the locked product decision) and replace it with the model below.

### 3.1 What "a strategy" is allowed to be

To shrink the attack surface before sandboxing it, strategies are authored against a **constrained, declarative-first strategy SDK**, not arbitrary Python. The agent assembles strategies from allowlisted DATA-LAYER tool calls + a small set of vetted quant primitives (the proven numpy logic ported from v1 `app/engine/` — signals, optimizer, attribution, risk model). Two execution modes:

1. **Declarative (preferred):** the strategy is a validated JSON/DSL graph of `{signal → construction → constraints → schedule}`. We execute it with *our* trusted interpreter. No user code runs at all. This is the safest and covers most strategies.
2. **Scripted (escape hatch):** if the agent needs custom logic, it submits Python that runs **only** inside the sandbox below, against a capability-restricted SDK surface — never with ambient `__builtins__`, network, or filesystem.

### 3.2 The sandbox (process + container + network + resource)

Every backtest and every live-paper strategy step runs in an **isolated, single-use worker** — *never* the control-plane/API process. Layers, outermost first:

1. **Separate host/pool.** Untrusted execution runs on a dedicated DigitalOcean worker pool, network-isolated from the control plane and the primary database. The control plane is never reachable from a strategy container.
2. **Per-job container** (gVisor/Kata or microVM — a syscall-filtering runtime, not bare Docker), one strategy job per container, destroyed after the job. No shared state between tenants or jobs.
3. **Network: deny-all egress by default.** No DNS, no outbound sockets. The strategy *cannot* call out. Market data and tool results are **pushed in** via a single authenticated stdin/IPC channel from a trusted broker process; results come back over the same channel as validated JSON only (this is exactly v1's review remedy: "marshal only validated JSON back"). If a future strategy needs a feed, it's an allowlisted, brokered, per-tenant-scoped capability — never raw network.
4. **Filesystem:** read-only root, a tmpfs scratch with a hard size cap, no host mounts, no secrets on disk.
5. **Resource limits (the v1 "unbounded IEX stream" / no-aggregate-deadline lesson):** cgroup CPU/memory/PID caps, plus **two clocks** — a per-tool-call timeout *and* an absolute wall-clock job deadline (e.g. backtest ≤ N min, each live step ≤ K s). When the aggregate budget is spent the job is killed and marked `deadline_exceeded`, never left to run past the ceiling. (v1 had per-call timeouts but no wall-clock budget — review §3.5.)
6. **Restricted interpreter:** stripped `__builtins__`, no `import` of anything outside the vetted SDK allowlist, seccomp profile denying `socket`/`ptrace`/`exec` family. Because egress is already denied at the network layer, an interpreter escape still hits a wall — **defense in depth, not a single guard** (the explicit anti-pattern from v1).
7. **No dynamic web/panel execution in the browser realm.** The web UI is observability-only (locked decision: chat console removed). It renders the agent's traces and results as **data**, never `new Function`/`eval` of model output. This deletes the v1 client-side `_TSX_BANNED`/`new Function` RCE (review §2 High) by construction.

### 3.3 Capability allowlisting

The sandbox SDK exposes a fixed, audited set of capabilities: `get_prices`, `get_fundamentals`, `compute_signal`, `optimize(weights, constraints)`, `place_paper_order`, `log`. Each is brokered by the trusted parent process, tenant-scoped, rate-limited, and audited. There is no `os`, no `subprocess`, no `open`, no `requests`. The strategy can only do what the platform offers — capabilities are *granted*, not *removed-from-a-denylist*.

---

## 4. Secrets, Audit Logging & Paper-Trading Guardrails

### 4.1 Secrets management

- **No secret in env vars committed/logged, no secret on a strategy container's disk.** Platform secrets (DO API token, model keys, future broker keys) live in a dedicated secrets manager (DO/Vault/cloud KMS-backed), fetched at runtime by the control plane only.
- **The control plane holds infra secrets; the runtime never sees them.** A strategy container is handed only short-lived, narrowly-scoped, per-job tokens (e.g. an object-store token scoped to `tenant/<id>/jobs/<jobid>/`), minted per job, expiring with the job.
- **Future broker keys (the seam, not built):** stored per-tenant, encrypted at rest with envelope encryption, decryptable only inside the brokerage-adapter process — *never* inside a strategy sandbox. The adapter is a separate, trusted, audited service behind the paper/live gate (§4.3).
- **Rotation:** all credentials (agent keys, infra tokens) rotatable without downtime; key revocation is immediate (the `keyid` lookup row is flipped, in-flight 15-min tokens are the max exposure).

### 4.2 Audit logging (append-only, tenant-attributed, retained)

v1 had an append-only audit table but the review flagged it grew unbounded and that "never-crash" swallowing erased trails (§3.2). v2:

- **Every** security-relevant event is logged: auth (key mint/use/revoke, login, device-link), every agent tool call (tool, args-digest, tenant, agent principal, result status, latency), every deploy job lifecycle, every paper order, every permission denial, every tenant-isolation violation caught by RLS.
- **Append-only by construction:** write-only table (no UPDATE/DELETE grant for the app role) or an external append-only sink (e.g. object-store WORM). Each record carries `tenant_id` (RLS-scoped reads) + the stable `agent_id`/`user_id` principal — attribution survives credential rotation (§1.1).
- **Tamper-evidence:** hash-chain each tenant's audit stream (`record.hash = sha256(prev_hash || payload)`) so deletion/reordering is detectable.
- **Retention:** explicit policy (e.g. 1y hot, then cold WORM), enforced by a scheduled job — *not* v1's lazy unbounded growth. Retention is configurable per-tenant for compliance.
- **No silent swallow:** the v1 "`except Exception: pass`" pattern that erased trails is banned on every audited path; failures to audit fail the operation (audit is on the critical path for money-touching actions).

### 4.3 Paper-trading guardrails — "paper can never accidentally touch real money"

Make it *structurally* impossible, not policy-impossible:

1. **`deploy:live` scope is not issuable at launch.** The code path to mint it is feature-flagged off. There is no credential in the system that can request live execution.
2. **Distinct, separately-deployed execution services.** Order routing goes through an `ExecutionAdapter` interface. The **only** implementation wired at launch is `PaperBook` (simulated fills against live market data). The `BrokerageAdapter` (real) is an interface/seam — *not implemented, not deployed, not in the dependency graph.* There is no binary path from a strategy to a real broker because the code isn't there.
3. **Explicit environment assertion.** Every order carries `mode: "paper"`. The paper book asserts `mode == "paper"` and the system carries a global `EXECUTION_MODE=paper` invariant checked at process start; any order lacking `paper` is rejected and audited as a critical anomaly.
4. **Visual + data labeling everywhere** (carrying forward the review's "data lineage / provenance badge" recommendation): every trade, position, and P&L in the UI and API is tagged `paper`. No path renders a paper fill as anything else.
5. **When live is eventually added:** it will require a separate, audited, MFA-gated, per-tenant opt-in, real broker key in the isolated adapter, and a distinct `deploy:live` scope — gated behind the same intersection model (§1.4). The seam is clean; the gate is closed.

---

## 5. Rate Limiting, Abuse/DoS & Aggregate Deadlines

### 5.1 Rate limiting on the public MCP surface

v1's limiter (`security.py`) was in-process per-IP — fine for a single node, but the review noted it's "not a substitute for an edge WAF." v2:

- **Edge WAF + L7 limiter** in front of the MCP/REST/SSE surface (IP and ASN reputation, slow-loris protection, body-size cap — keep v1's `BodySizeLimitMiddleware`).
- **Distributed, principal-scoped quotas** (Redis token-bucket, shared across nodes — not v1's per-process dict). Limits are keyed by **`tenant_id` + `agent_id`**, not just IP, since agents come from arbitrary IPs. Tiered:
  - per-credential request rate,
  - per-tenant aggregate rate,
  - **per-tool cost budgets** — expensive DATA-LAYER tools (backtests, factor models, large tick pulls) carry a higher "cost" and draw down a per-tenant compute budget, so one agent can't amplify cheap-looking calls into a resource DoS.
- **Concurrent-job caps per tenant** on the deploy layer (bounded backtests/live strategies) so a tenant can't exhaust the worker pool.
- Limits **fail closed and return `429` with `Retry-After`** (v1 pattern, kept). Never disabled in production (v1 disabled under pytest via env — fine for tests, but the prod path must always be on).

### 5.2 Aggregate request deadlines (direct v1 fix)

v1's #5 systemic flaw: "per-call timeouts exist but aggregate budgets don't" (orchestrator 90s past a 60s proxy ceiling, unbounded IEX stream). v2 makes **wall-clock budgets first-class**:

- Every MCP request and every deploy job opens with an **absolute deadline** set at entry. Each downstream call (tool, DB, sandbox step) gets a **shrinking** per-call timeout = `min(call_default, remaining_budget)`. When the budget is exhausted, the request returns a structured `deadline_exceeded` immediately rather than chaining past the ceiling.
- Long jobs (backtests) run **async** with a job handle + SSE/poll status (with heartbeats — v1's review flagged blocking SSE with no keepalive), not a single blocking request, so they're never bounded by the HTTP proxy ceiling at all.

### 5.3 Abuse/DoS specifics

- Auth endpoints: strict per-IP + per-account limits, exponential backoff, lockout + alert on credential-stuffing patterns. Constant-time key compare (no timing oracle on `keyid`→hash lookup).
- Leaked-key scanning (the `ith_live_` prefix is grep-able) + auto-revoke on detection.
- Anomaly detection on the audit stream (sudden cross-tool fan-out, deadline-exceeded clusters, RLS-denial spikes → throttle + alert).

### 5.4 Tests that actually gate (cross-cutting, v1 lesson #6)

Security is only real if it's enforced in CI. v1 ran 3 of 33 suites and the paths that shipped weren't tested. v2 **gates merge** on: RLS-coverage test (§2.2, every tenant table has a policy + NOT NULL `tenant_id`); a cross-tenant access test that *asserts* tenant B cannot read/write tenant A's rows, jobs, or artifacts; a sandbox-escape test battery (no network egress, no fs write, no banned import, deadline kills a runaway job); a "no real-broker in the dependency graph" assertion (§4.3); and an auth/scope-intersection matrix test. **No green, no merge.** These tests run the *production* code paths (not stubbed-out SQL or AI-disabled paths — the v1 anti-pattern).

---

## Summary: each v1 systemic flaw → v2 structural fix

| v1 systemic flaw (review §3) | v2 structural answer |
|---|---|
| Static-guard-then-trust → 2 RCEs | No in-process eval of untrusted code; out-of-process, network-denied, rlimited sandbox; declarative-first SDK; capabilities granted not denylisted (§3) |
| Tenancy per-call-site, not invariant | Postgres RLS as the un-forgettable backstop + scoped data layer with no raw query + CI fails on any unscoped table (§2) |
| Unlocked read-modify-write on money path | All mutations through `SELECT … FOR UPDATE` / optimistic-version transactions via the single `TenantSession`; carried over from v1's correct `state.py` pattern (§2.2) |
| Per-call timeouts, no aggregate deadline | Absolute wall-clock budget per request/job; shrinking per-call timeouts; async long jobs with heartbeats (§5.2) |
| Tests exist but don't gate | RLS-coverage, cross-tenant, sandbox-escape, paper-only, and scope-matrix tests gate merge against production paths (§5.4) |
| (new) BYO machine principal | Agent is a first-class, separately-credentialed, scope-limited principal distinct from the human; effective perm = role ∩ scope ∩ tenant (§1) |
| (new) accidental real money | Paper-only by construction: `deploy:live` unissuable, real adapter not in the dependency graph, `mode:"paper"` invariant asserted, everything labeled (§4.3) |

**Highest-risk surface remains strategy execution (§3)** — treat the sandbox as the load-bearing control: assume the interpreter restriction *will* be bypassed and ensure that even then the attacker is in a network-denied, secret-free, per-job, destroyed-after-use microVM that cannot address the control plane, the primary DB, or another tenant's prefix.

Relevant v1 files that inform (and whose patterns are kept or replaced) the design:
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/api-server/app/tenant.py` (contextvar scoping — kept as convenience, RLS added as guarantee)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/api-server/app/auth.py` and `permissions.py` (token/role discipline — kept and extended with agent scopes)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/api-server/app/security.py` (rate-limit/headers — replaced with distributed principal-scoped limits + edge WAF)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/api-server/app/state.py` (correct `FOR UPDATE` pattern — generalized into the scoped data layer)
- `/Users/joshuajerin/Desktop/jarvis/ithaca/artifacts/api-server/app/dynamic_skills.py` and `code_guard.py` (the v1 RCE path — dropped entirely, replaced by §3)