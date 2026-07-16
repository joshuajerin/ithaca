# Ithaca v2 — single multi-service CPU image.
#
# ONE lean image runs all four services (the workspace is path-linked, so one
# `uv sync` builds the whole product). The container's ROLE is chosen by the
# command/args at run time — see `deploy/entrypoint.sh` and the targets below:
#
#   mcp-gateway     :  ithaca-mcp        (python -m ithaca_mcp)         MCP tools
#   rest-gateway    :  ithaca-rest       (uvicorn ithaca_rest.app:app)  REST + SSE
#   control-plane   :  ithaca-control    (uvicorn ithaca_control.app)   money-path writer
#   conductor       :  ithaca-conductor  (python scripts/run_workers.py)  backtest worker + paper scheduler
#   trigger-engine  :  ithaca-trigger    (python -m ithaca_runtime.trigger_engine)
#   backtest-worker :  dedicated durable backtest queue worker
#   backtest-runner :  ithaca-backtest   (python -m ithaca_runtime.backtest_runner)
#   live-runner     :  ithaca-live       (python -m ithaca_runtime.live_runner)
#
# CPU-ONLY: base is python:3.12-slim (no CUDA, no GPU libs). numpy is the only
# heavy dep and runs on CPU.

# ---------------------------------------------------------------------------
# Stage 1 — builder: install uv, sync the workspace into a self-contained venv.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# uv: fast, reproducible installs. Pinned version, installed via pip (no extra
# registry dependency than the Python base image's index).
RUN pip install --no-cache-dir uv==0.7.13

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# 1) Copy ONLY the manifests + lockfile first so the dependency layer caches and
#    is not invalidated by source edits. The workspace members must exist for uv
#    to resolve the path sources, so we copy their pyproject.toml stubs too.
COPY pyproject.toml uv.lock ./
COPY packages/contracts/py/pyproject.toml packages/contracts/py/
COPY ithaca-core/pyproject.toml ithaca-core/
COPY services/platform/pyproject.toml services/platform/
COPY services/mcp-gateway/pyproject.toml services/mcp-gateway/
COPY services/control-plane/pyproject.toml services/control-plane/
COPY services/rest-gateway/pyproject.toml services/rest-gateway/
COPY services/runtime/pyproject.toml services/runtime/
COPY services/ibkr-engine/pyproject.toml services/ibkr-engine/

# 2) Resolve + install all third-party deps for every workspace package, against
#    the frozen lockfile, WITHOUT the local packages (no source yet). Cached.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --all-packages

# 3) Now copy the actual source and install the workspace packages themselves.
COPY packages/ packages/
COPY ithaca-core/ ithaca-core/
COPY services/ services/
COPY scripts/ scripts/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-packages

# ---------------------------------------------------------------------------
# Stage 2 — web builder: build the React/Vite observability UI.
# The built dist is copied into the runtime image; the rest-gateway serves it
# as static files at / so the UI and the API share one LB endpoint.
# VITE_* vars are baked into the JS bundle at build time. Pass Clerk's
# publishable value through a neutral build arg so Docker secret scanners do not
# treat the public browser key name as secret material.
# --build-arg CLERK_PUBLISHABLE_VALUE=...
# ---------------------------------------------------------------------------
FROM node:24-slim AS web-builder

ARG CLERK_PUBLISHABLE_VALUE=""
ARG VITE_API_BASE="/api"

# Production images must never contain the unauthenticated fallback shell.
# Clerk publishable keys are public browser configuration, but they still have
# to be present while Vite builds because VITE_* values are compiled into JS.
RUN case "${CLERK_PUBLISHABLE_VALUE}" in \
      pk_test_*|pk_live_*) ;; \
      *) echo "CLERK_PUBLISHABLE_VALUE must be a Clerk pk_test_ or pk_live_ publishable key" >&2; exit 1 ;; \
    esac

# Install pnpm
RUN corepack enable && corepack prepare pnpm@10.30.1 --activate

WORKDIR /app

# Copy workspace manifests for dependency caching.
# All three workspace packages (web, site, packages/contracts/ts) must have their
# package.json present so pnpm workspace resolution succeeds with --frozen-lockfile.
# site/ is built by Vercel, not here — only its manifest is needed for pnpm.
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/contracts/ts/package.json packages/contracts/ts/
COPY web/package.json web/
COPY site/package.json site/

# Install with scripts disabled first, then rebuild esbuild explicitly
# (pnpm's build-script security prompt blocks --frozen-lockfile in CI otherwise)
RUN pnpm install --frozen-lockfile --ignore-scripts && \
    pnpm rebuild esbuild

# Copy source and build
COPY packages/contracts/ packages/contracts/
COPY web/ web/

RUN VITE_CLERK_PUBLISHABLE_KEY="${CLERK_PUBLISHABLE_VALUE}" \
    VITE_API_BASE="${VITE_API_BASE}" \
    pnpm --filter @ithaca/web run build && \
    grep -R -F "${CLERK_PUBLISHABLE_VALUE}" /app/web/dist/assets >/dev/null && \
    ! grep -R -i -F "Doomberg" /app/web/dist

# ---------------------------------------------------------------------------
# Stage 3 — runtime: copy the venv + the app source onto a clean slim base.
# No build tooling, no uv, no caches. Non-root.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Run as an unprivileged user (matches the pod securityContext runAsNonRoot).
RUN groupadd --system --gid 10001 ithaca \
    && useradd  --system --uid 10001 --gid ithaca --home-dir /app --no-create-home ithaca

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Default system-of-record DSN; overridden in-cluster to the Managed PG DSN.
    ITHACA_DB=":memory:"

WORKDIR /app

# The synced virtualenv (all deps + the workspace packages, importable).
COPY --from=builder /opt/venv /opt/venv
# Application source needed at run time (scripts/ for the conductor + loader).
COPY --from=builder /app/scripts /app/scripts
# Source trees are installed editable into the venv; copy them so imports + the
# loader script resolve. (No data/, no tests, no node_modules — see .dockerignore.)
COPY --from=builder /app/ithaca-core /app/ithaca-core
COPY --from=builder /app/services /app/services
COPY --from=builder /app/packages /app/packages

# Built web UI — the rest-gateway serves this at / via StaticFiles.
# ITHACA_WEB_DIST env var points the gateway here; it's set in entrypoint.sh.
COPY --from=web-builder /app/web/dist /app/web/dist

COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER ithaca

# Default role = the conductor (singleton/interactive loops). Override the
# CMD (or pass a role arg to the entrypoint) to run a different service.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["conductor"]
