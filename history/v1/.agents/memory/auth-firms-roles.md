---
name: Auth / firms / roles foundation
description: Identity layer for the terminal (firm signup, login, durable sessions, protected API) and its non-obvious traps.
---

# Auth / firms / roles foundation

Multi-tenant identity: firms (tenants) → users (email/password, one firm each) → roles (admin/trader/analyst/read-only). First user of a firm signup is the firm admin.

## Architecture
- `app/auth.py`: stdlib PBKDF2-HMAC-SHA256. `hash_password(pw) -> (hash_hex, salt_hex)`; `verify_password(pw, hash_hex, salt_hex)`; `new_session_token()` + `hash_token()` (store the HASH, never the raw token); `COOKIE_NAME="at_session"`, 30-day TTL.
- `app/auth_store.py`: firms/users/auth_sessions, DB-first `CREATE TABLE IF NOT EXISTS` + in-memory fallback (same runtime-DDL pattern as strategy desk — NOT drizzle push). Drizzle mirror in `lib/db/src/schema/auth.ts` is for convention only.
- `main.py`: `require_identity` resolves the session from the httpOnly `at_session` cookie OR an `Authorization: Bearer <token>` header (cookie wins; same hash+lookup) → 401 if neither valid. Two routers: `public = APIRouter(prefix="/api")` (healthz + /auth/signup,login,logout,user) vs `api = APIRouter(prefix="/api", dependencies=[Depends(require_identity)])` for everything else. The Bearer path exists so non-browser/test clients with no cookie jar can authenticate — the generated client attaches it via `setAuthTokenGetter`.

## Traps (cost real time)
- **Secure cookie + http TestClient = silent 401s.** The session cookie is `secure=True` (correct for the https Replit proxy/preview). `TestClient(app)` uses `http://testserver`, so the cookie sits in the jar but is never replayed → every authed probe spuriously 401s. Fix: `TestClient(app, base_url="https://testserver")`. Same fix was needed in `test_smoke.py` once orchestrate became protected.
- **Protecting orchestrate breaks the existing smoke test.** Any pre-existing test hitting a now-protected route must sign up first to get a session cookie.
- **orval LogoutResponse collision.** Orval auto-generates a `LogoutResponse` zod validator for the `logout` op, so the response *schema* had to be named `LogoutResult` in openapi.yaml/models.py to avoid a clash.
- **Stale composite `dist/*.d.ts` for api-client-react.** `ApiError` is exported from `src/index.ts`, but terminal tsc resolves the composite project's emitted `dist/index.d.ts`. After adding a new re-export, run `pnpm run typecheck:libs` (`tsc --build`) to refresh dist or tsc reports "no exported member 'ApiError'". Runtime is unaffected (vite uses the exports map → src).

**Why:** these are environment/tooling quirks not visible in the code; each produced a confusing failure (auth works in browser but tests 401; type error on a symbol that is clearly exported).
