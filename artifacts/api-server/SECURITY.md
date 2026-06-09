# Agentic Terminal API — Security Posture & Threat Model

This document records the security controls on the `api-server` artifact, the
threats they address, and the residual risks an institutional operator should be
aware of. **Server-side enforcement is authoritative**; any frontend gating
(hidden buttons, disabled controls) is convenience only.

Last reviewed: 2026-06-09.

---

## 1. Trust boundaries

| Zone | Description | Trust |
| --- | --- | --- |
| Browser SPA (`artifacts/terminal`) | Untrusted. All input is attacker-controllable. | none |
| Replit edge proxy | Terminates TLS, path-routes to the artifact, injects `X-Forwarded-For`. | infrastructure |
| `api-server` (FastAPI) | The authority. Enforces authn/authz, validation, limits. | trusted |
| PostgreSQL | Holds firms, users, sessions, per-firm settings, app state. | trusted store |
| Upstream data feeds (Yahoo, FRED, US Treasury, SEC EDGAR, IEX, Polymarket) | Untrusted external data. Parsed defensively. | none |
| OpenAI via Replit AI Integrations proxy | Trusted transport; **its output is untrusted** (treated as data, validated before any execution). | none for outputs |

Tenancy model: every authenticated request resolves to an `Identity` of
`{user_id, firm_id, role}`. The firm is the tenant boundary.

---

## 2. Identity, authentication & authorization

- **Authentication.** All non-public routes hang off a router that depends on
  `require_identity` (`app/main.py`). It resolves the caller from the httpOnly
  `at_session` cookie (or an `Authorization: Bearer` token for non-browser
  clients) via a hashed-token session lookup. No/invalid/expired token → `401`
  before any handler runs. Only `/api/healthz`, `/api/auth/signup`,
  `/api/auth/login` are public.
- **Sessions.** Tokens are random and stored only as a hash; the cookie is
  `httpOnly`, `Secure`, `SameSite`. Logout revokes the session server-side.
- **Passwords.** Salted hash with a constant-time compare (`app/auth.py`).
- **Authorization (RBAC).** `require_role(*roles)` builds on `require_identity`
  and returns `403` if the caller's role is not allowed. The first user of a
  firm is `admin`; others default to `analyst`.
- **Tenant isolation.** Handlers operate within `identity.firm_id`. Generated AI
  code cannot reach the DB or other firms' data at all (see §4).

---

## 3. Transport & application hardening

Implemented in `app/security.py`, wired in `app/main.py`:

- **CORS allow-list, never `*`.** `allowed_origins()` derives the explicit origin
  list from `REPLIT_DOMAINS` / `REPLIT_DEV_DOMAIN`. `allow_credentials=True` is
  therefore safe (a wildcard + credentials is forbidden by browsers and was the
  prior misconfiguration). Methods restricted to `GET/POST/DELETE/OPTIONS`.
- **Security headers on every response** (`SecurityHeadersMiddleware`), including
  error/401 responses:
  - `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'`
  - `Referrer-Policy: no-referrer`
  - `Permissions-Policy` disabling geolocation/mic/camera/payment
  - `Cross-Origin-Opener-Policy: same-origin`
  - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'`
    — appropriate for a JSON API that never renders HTML.
- **Request body cap** (`BodySizeLimitMiddleware`): rejects bodies over
  `MAX_BODY_BYTES` (default 16 MiB) with `413` before reaching a handler. Sized
  to allow a short base64 voice clip on `/transcribe` while blocking body-bombs.
- **Rate limiting** (`rate_limit` dependency, sliding window per client IP):
  | Bucket | Endpoint(s) | Limit |
  | --- | --- | --- |
  | `auth` | `/auth/login`, `/auth/signup` | 10 / 60s |
  | `orchestrate` | `/orchestrate`, `/orchestrate/stream` | 30 / 60s |
  | `feature-request` | `/feature-request` | 10 / 60s |
  | `speak` | `/speak` | 60 / 60s |
  | `transcribe` | `/transcribe` | 60 / 60s |
  Exceeding a bucket returns `429` with `Retry-After`. Auto-disabled under the
  test runner (`PYTEST_CURRENT_TEST`) or `TERMINAL_RATELIMIT_DISABLED=1`.

---

## 4. AI code-execution containment (highest-value control)

The self-building feature pipeline (`/feature-request`) lets an admin describe a
panel and has the LLM author **and run** new Python + TSX. This is the single
highest-risk surface; it is contained in depth:

1. **Authorization gate.** `/feature-request` and `DELETE /features/{type}`
   require the `admin` role (`require_codegen_enabled` → `require_role("admin")`).
2. **Per-firm kill-switch.** `app/firm_settings.py` stores a `codegen_enabled`
   flag per firm (DB-backed, default on). Any admin can disable AI code
   execution for the whole firm via `POST /api/firm/settings`; while off,
   `/feature-request` returns `403`.
3. **Input bound.** Feature descriptions are capped (2000 chars) and rate-limited.
4. **Static allow-list validation** (`app/code_guard.py`). Generated Python is
   parsed to an AST and rejected unless it conforms to a strict allow-list:
   - imports limited to a vetted set of stdlib/data roots; **no** `os`,
     networking, `subprocess`, `app.*`, DB drivers, or filesystem modules;
   - **no** dynamic execution (`eval`, `exec`, `compile`, `__import__`),
     attribute-based escapes, or dunder access.
   Because the allow-list excludes `os`, networking, and `app.*`, generated code
   **cannot read environment secrets, open sockets, or touch the database / other
   firms' data** — containment is structural, not heuristic.
5. **Isolated validation subprocess** (`app/feature_builder.py`). Candidate code
   is imported and exercised in a separate `python -I` subprocess with a clean
   env, POSIX resource limits (CPU/memory/file-size), no network, and a wall-clock
   timeout. Failure leaves **no** partial files (atomic write-or-rollback). This
   subprocess call is annotated `# nosemgrep` — its argv is a static list and it
   *is* the sandbox, not an injection sink.

> Note: validated features run **in-process** afterwards (no server restart), so
> the static guard + sandbox validation are the security boundary. The guard is
> deliberately conservative — it is easier to widen the allow-list later than to
> recover from an escape.

---

## 5. Secrets & logging hygiene

- All credentials (`SESSION_SECRET`, `AI_INTEGRATIONS_*`, `FRED_API_KEY`,
  `DATABASE_URL`/`PG*`) are read from the environment via `os.environ` — none are
  hard-coded. The HoundDog PII/secrets scan reports **0** findings.
- API keys are never logged. Provider clients read keys at call time and log only
  status/latency, never request bodies or auth material.
- Session tokens are logged/stored only as hashes.

---

## 6. Dependency & SAST scan results (2026-06-09)

- **Dependency audit:** 0 critical, 0 high, 1 moderate (transitive). No
  critical/high to remediate.
- **SAST (semgrep):** 0 critical, **0 high** after this pass. Resolved this pass:
  - Switched external XML parsing (`app/sources/edgar.py`,
    `app/sources/thirteenf.py`) from stdlib `xml.etree` to **`defusedxml`** to
    remove the XXE / entity-expansion (billion-laughs) risk on untrusted SEC
    feeds.
  - Triaged + suppressed confirmed false positives: the validation
    `subprocess.run` (the sandbox itself, static argv) and five `generic-api-key`
    hits that are plain numeric constants (e.g. `DEFAULT_CAPITAL = 1_000_000.0`),
    not secrets.
- **HoundDog (PII/secrets):** 0 findings.

### Accepted residual (MEDIUM, out of critical/high scope)

- `insecure-hash-algorithm` (MD5/SHA1) in `app/data.py`, `app/sources/{congress,news,sentiment}.py`:
  used only for **non-cryptographic** content/dedup cache keys, not for security.
  Acceptable; could be migrated to SHA-256 opportunistically.
- `detect-non-literal-regexp` / `unsafe-dynamic-method` in frontend artifacts:
  client-side, low impact; the API does not trust the client regardless.

---

## 7. Known residual risks / non-goals

- **Single-node limits.** Rate limiting and the body cap are in-process. They are
  defense-in-depth against cost/abuse, **not** a substitute for an edge WAF or a
  distributed limiter. A multi-replica deployment should add an edge layer.
- **AI output quality.** Containment prevents a generated feature from causing
  *harm*; it does not guarantee the feature is *correct*. Admins own what they
  build.
- **Upstream data integrity.** External feeds can be wrong or unavailable. The
  app reports source/`asOf`/coverage and never silently imputes, but it trusts
  the *values* those providers return.
- **Self-build is in-process.** A future hardening step would move execution of
  validated features into a persistent isolated worker rather than the API
  process.
