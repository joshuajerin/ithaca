# Onboarding to Ithaca v2

Ithaca v2 is a multi-tenant platform for **bring-your-own (BYO) agents**: an external agent
(or a human in the web UI) authors strategies, requests backtests and paper deployments, and
watches the whole thing happen on a gap-free, tenant-isolated trace. This guide takes you from
"no account" to a live paper deployment you can observe.

The whole loop is demonstrated, offline and deterministically, by
[`scripts/demo_full_circle.py`](../scripts/demo_full_circle.py) — run it to see every step:

```bash
uv run python scripts/demo_full_circle.py
```

---

## 1. Create a tenant

A **tenant** is the single hard isolation key: every run, strategy, trace event, and paper
book carries it, and every query filters by it. Tenants are created by an operator through the
admin endpoints on the control plane, which are gated behind `ITHACA_ADMIN_TOKEN`.

> If `ITHACA_ADMIN_TOKEN` is **unset**, the admin endpoints return `404` and are completely
> inert — they don't exist for dev or tests. Set it (to a strong random value) only on the
> operator's control-plane process to enable onboarding.

```bash
export ITHACA_ADMIN_TOKEN="<operator-secret>"

# Create the tenant
curl -sX POST http://localhost:8000/admin/tenants \
  -H "X-Admin-Token: $ITHACA_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Capital"}'
# -> {"tenant_id": "…uuid…", "name": "Acme Capital"}
```

## 2. Mint an API key

A key is a **rotatable credential** carrying capability scopes. The plaintext is shown
**exactly once** at mint time and is unrecoverable thereafter — store it in your secret
manager immediately.

```bash
curl -sX POST http://localhost:8000/admin/tenants/<tenant_id>/keys \
  -H "X-Admin-Token: $ITHACA_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scopes": ["data:read", "strategy:author", "deploy:backtest", "deploy:paper"]}'
# -> {"key_id": "…", "api_key": "ith_<env>_<keyid>_<secret>", "scopes": [...]}
```

### Key format

```
ith_<env>_<keyid>_<secret>
```

| segment    | meaning                                                                    |
|------------|----------------------------------------------------------------------------|
| `ith`      | fixed prefix.                                                               |
| `<env>`    | deployment env tag (`test` by default, `prod` in production).             |
| `<keyid>`  | the public, stable credential id. **Audit attributes to this.** Revoking it does not rotate the principal. |
| `<secret>` | high-entropy token. **Never stored** — only `sha256(salt + secret)` is persisted, so a database leak cannot reconstruct a usable key. |

Verification is constant-time and revocation-aware; a bad or revoked key is a hard `401`.

## 3. Point your agent / the UI at the platform

Every call goes to the **same front door** (the control plane for writes; the rest-gateway for
the UI/observability). Authenticate with the bearer key:

```
Authorization: Bearer ith_<env>_<keyid>_<secret>
```

The gateway derives the **tenant from the key** — it is authoritative, so you never send a
tenant id alongside a key.

**Web UI:** set `VITE_API_KEY` at build/dev time. When present, the UI sends
`Authorization: Bearer <key>` on every request; when absent it falls back to the local-dev
`X-Tenant-Id` header (default tenant `00000000-0000-0000-0000-000000000001`). The live trace
stream uses Server-Sent Events, which cannot set headers; in local dev it carries the tenant
as a `?tenant_id=` query param. (A query-token / cookie session for keyed SSE is a future
phase.)

## 4. The loop: propose → backtest → promote → observe

Each step is enforced by the scope on your key **and** by the actor rule on the money path:

1. **Propose** a strategy spec — needs `strategy:author`.
   `POST /api/strategies` (UI) or `POST /strategies` (control plane).
2. **Backtest** — needs `deploy:backtest`. `POST /runs {"kind": "backtest"}` lands the run
   `queued`; the conductor (a backtest worker) pulls the queue and runs it to `succeeded`.
3. **Request a paper deployment** — needs `deploy:paper`. `POST /runs {"kind": "paper"}`.
   `deploy:paper` means *"may **request** a paper deployment that requires human
   acceptance"* — it does **not** grant self-promotion.
4. **Promote + activate** — a **human** action. An agent key (an `agent` actor) is refused
   `403` here no matter its scopes; a human (`user` actor, e.g. via the UI) promotes through
   the compliance + risk gate, then activates the deployment to `live`. The paper scheduler
   then ticks it and the control plane's single writer applies the book under the gate.
5. **Observe** — `GET /api/runs/{id}` returns the run plus its gap-free trace; the live tail is
   `GET /api/runs/{id}/events` (SSE); `GET /api/runs/{id}/book` is the paper position book.

## Scopes model

Effective permission = **role ∩ scopes ∩ tenant**. The launch scope set:

| scope             | grants                                                              |
|-------------------|---------------------------------------------------------------------|
| `data:read`       | read runs, strategies, traces, and books (the observability surface).|
| `strategy:author` | author/propose a strategy spec.                                     |
| `deploy:backtest` | request a backtest run.                                             |
| `deploy:paper`    | **request** a paper deployment (still requires human promotion).    |

`deploy:live` and broker connectivity are **intentionally not issuable** at launch — the
platform is paper-only by construction. The two invariants that make this safe:

- **No self-promotion.** Only a human actor may promote/activate/pause/resume/retire a
  deployment. An agent can request, never accept.
- **Single writer, re-gated.** The control plane is the only writer of the money path; it
  re-runs the compliance + risk gate before applying any book, so a bad proposal cannot trade.

## How the UI is served in production

The rest-gateway serves the built web app (`web/dist`) as static files at `/`, behind the
**same load balancer** as the API — one origin for both UI and `/api/*`. The static mount is
registered **last**, so `/api/*` and `/healthz` always take precedence; client-side routes
fall through to `index.html`. If no build is present (dev / tests) the mount is skipped and the
gateway still starts as an API-only backend. Point the image at a prebuilt bundle with
`ITHACA_WEB_DIST=/abs/path/to/dist` (defaults to the repo-relative `web/dist`).

Build the UI with:

```bash
pnpm --filter @ithaca/web run build
```
