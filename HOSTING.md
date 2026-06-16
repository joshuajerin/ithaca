# Shared hosting: doomberg.me + kural.website

Both sites are served from **one Vercel project** (`doomberg`, Saber team
`sabers-projects-2821dd35`) and share **one Supabase project**. AI calls are
proxied through Vercel serverless functions to a Hermes (Jarvis) backend — the
same pattern as the existing Cloudflare custom-endpoint setup.

## Architecture

```
browser (doomberg.me / kural.website)
        │  POST /api/ai/<site>   (no credentials)
        ▼
Vercel serverless fn  (api/ai/doomberg.js | api/ai/kural.js)
        │  adds Authorization: Bearer <site key>   (server-side env)
        ▼
Hermes custom-endpoint tunnel  (HERMES_BASE_URL)  → /doomberg | /kural sandbox
        ▼
Hermes agent (isolated session + system prompt per site)
```

Supabase is shared the same way: one database, every row carries a `site`
column (`doomberg` | `kural`). Server-side functions use the service-role key;
the browser never sees it.

## Files

| Path | Role |
|------|------|
| `api/[...path].js` | Catch-all API: tenant detection, all routes, Hermes proxy, Supabase logging |
| `supabase/schema.sql` | Shared schema (tenants, ai_interactions, saved_dashboards) + RLS |
| `scripts/smoke-ai-proxy.mjs` | Secret-free smoke test of the catch-all per-tenant routing |
| `.env.example` | Env contract for the Vercel project |

## Required Vercel env vars (server-side, NOT `VITE_`)

```
HERMES_BASE_URL            https://<tunnel-host>
DOOMBERG_HERMES_KEY        <bearer for Hermes /doomberg>
KURAL_HERMES_KEY           <bearer for Hermes /kural>
SUPABASE_URL               https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY  <service-role key>
```

Set them with:

```bash
vercel env add HERMES_BASE_URL production --scope sabers-projects-2821dd35
# ...repeat per var, or paste from .env.example
```

## Hermes backend (already live)

The Hermes side runs on the ops box as systemd user services:

- `hermes-api-portfoliowebsite.service` — Hermes API backend on `127.0.0.1:8652`
- `jarvis-custom-endpoint-api.service` — wrapper on `127.0.0.1:8651`, config at
  `~/.hermes/custom_endpoint_api/config.json` (endpoints `/doomberg`, `/kural`,
  `/portfolio-website`)
- `jarvis-custom-endpoint-tunnel.service` — `cloudflared` public tunnel; current
  URL in `~/.hermes/custom_endpoint_api/public_url.txt`

Health: `GET <tunnel>/health` lists configured endpoints + backend status.

> trycloudflare URLs rotate on restart. For a stable production hostname, move
> to a named Cloudflare Tunnel and update `HERMES_BASE_URL`.

## Supabase setup

1. Create one Supabase project (shared by both sites).
2. Apply the schema:
   ```bash
   supabase link --project-ref <ref>
   supabase db push
   ```
   or paste `supabase/schema.sql` into the SQL editor.
3. Put `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` in the Vercel project env.

## GitHub auto-deploy

`vercel git connect` requires a GitHub Login Connection on the Saber Vercel
account. Add it once at
<https://vercel.com/account/login-connections>, then:

```bash
vercel git connect https://github.com/joshuajerin/doomberg.git \
  --scope sabers-projects-2821dd35
```

Until then, deploy from CLI:

```bash
vercel deploy --prod --scope sabers-projects-2821dd35
```
