---
name: Python backend on api-server artifact
description: How to run a Python/FastAPI service inside the shared `api-server` artifact instead of the default TS Express server.
---

The shared `api-server` artifact defaults to a TypeScript Express server. It can be
repointed to a Python (FastAPI + uvicorn) service while keeping the same `/api` path
mounting that the proxy and generated frontend client expect.

Key facts (durable, not obvious):

- **Code lives under `artifacts/api-server/app/`** as a package (`app/main.py` with
  `app = FastAPI()`), served under the `/api` prefix via an `APIRouter(prefix="/api")`.
- **uvicorn must use `--app-dir artifacts/api-server`** so that `app.main:app` resolves.
  The directory name `api-server` contains a hyphen, so you cannot import it as
  `artifacts.api-server.app.main`; `--app-dir` adds the artifact dir to sys.path instead.
- **Dev run** is a shell string in `artifact.toml`, so `$PORT` is shell-expanded:
  `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir artifacts/api-server --reload`.
  **Production run** is an args array (no shell), so set `PORT` via `[services.production.run.env]`
  and hardcode `--port 8080`. No build step is needed (remove the TS build block).
- **Restart the workflow after swapping artifact.toml.** `verifyAndReplaceArtifactToml`
  updates config but the already-running process keeps the OLD run command until the
  workflow is restarted. Symptom: health/endpoints still answer like the previous server
  (e.g. Express `Cannot GET /api/...` 404s) after the swap.
- **Why:** keeping the service under `/api` on localPort 8080 means the existing proxy
  routing and the orval-generated React Query client (which call `/api/...`) work unchanged
  — no frontend or proxy edits required when switching the server language.
- AI access in Python: point the `openai` SDK at the Replit proxy via
  `OpenAI(base_url=os.environ["AI_INTEGRATIONS_OPENAI_BASE_URL"], api_key=os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"])`.
  Model `gpt-5.4`; use `max_completion_tokens` (NOT `max_tokens`); do not set `temperature`.
