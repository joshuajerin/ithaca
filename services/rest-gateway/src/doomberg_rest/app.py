"""FastAPI app — the web UI's ONLY backend (the browser never speaks MCP).

Reads (tenant-scoped, observability):
  - ``GET  /api/runs``                 list runs for the tenant (optional ?kind=).
  - ``GET  /api/runs/{id}``            one run + its shaped trace (run + three lanes + events).
  - ``GET  /api/runs/{id}/book``       the live paper book (positions) for a deployment.
  - ``GET  /api/strategies``           list the tenant's strategies (latest version each).
  - ``GET  /api/runs/{id}/events``     SSE: replay-from-seq (Last-Event-ID) then live tail.

Human money-path actions (the UI's buttons). These are NOT a second money path: they call the
SAME ``doomberg_control.actions`` functions the control plane exposes, over the same stores, so
there is one implementation of every write no matter which surface a human used:
  - ``POST /api/strategies``                  propose a spec.
  - ``POST /api/runs``                         create a run (queued).
  - ``POST /api/runs/{id}/{promote|activate|pause|resume|retire}``  paper lifecycle.

Tenant isolation: ``X-Tenant-Id`` (header) or ``?tenant_id=`` (EventSource can't set headers)
is required and threaded into every store call as the first arg. No unscoped read path exists.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from doomberg_control import actions
from doomberg_control.actions import ActionError
from doomberg_control.deps import Ctx
from doomberg_core import Core
from doomberg_platform import BookStore, RunStore, StrategyStore, TraceStore, open_db

from .readmodel import shape_run, shape_run_row
from .sse import event_stream, parse_last_event_id


class Stores:
    """The platform store quartet + a core, all sharing one db handle.

    This object IS a valid ``platform`` for ``doomberg_control.actions`` (it exposes
    ``runs``/``strategies``/``trace``/``books``), so the UI's write routes reuse the control
    plane's single money-path implementation in-process.
    """

    def __init__(self, db: Any) -> None:
        self.db = db
        self.runs = RunStore(db)
        self.strategies = StrategyStore(db)
        self.trace = TraceStore(db)
        self.books = BookStore(db)
        self.core = Core()


class ProposeBody(BaseModel):
    spec: dict[str, Any]


class CreateRunBody(BaseModel):
    strategy_id: str
    kind: str = "backtest"
    range: str = "1y"


def require_tenant(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    tenant_id: str | None = Query(default=None),
) -> str:
    """Tenant from the ``X-Tenant-Id`` header, or the ``?tenant_id=`` query (EventSource).

    No tenant => 400. We never fall back to an unscoped query (the hard isolation rule).
    """
    resolved = x_tenant_id or tenant_id
    if not resolved:
        raise HTTPException(status_code=400, detail="X-Tenant-Id header (or ?tenant_id=) is required")
    return resolved


def _ctx(
    tenant_id: str = Depends(require_tenant),
    x_actor_kind: str | None = Header(default=None, alias="X-Actor-Kind"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
) -> Ctx:
    """The UI acts on behalf of a human, so the actor defaults to ``user`` (may promote)."""
    return Ctx(
        tenant_id=tenant_id,
        actor_kind=(x_actor_kind or "user").strip().lower(),
        actor_id=(x_actor_id or "ui").strip() or "ui",
    )


def _do(fn, *args) -> dict[str, Any]:
    try:
        return fn(*args)
    except ActionError as err:
        raise HTTPException(status_code=err.status, detail=err.detail) from err


def create_app(db: Any | None = None) -> FastAPI:
    if db is None:
        db = open_db(os.environ.get("DOOMBERG_DB", ":memory:"))
    stores = Stores(db)

    app = FastAPI(title="doomberg-rest-gateway", version="0.0.0")
    app.state.stores = stores

    # Permissive CORS for local dev only. PIN allowed origins in prod.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Last-Event-ID"],
    )

    def get_stores(request: Request) -> Stores:
        return request.app.state.stores

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # ---- reads -------------------------------------------------------------------------
    @app.get("/api/runs")
    def list_runs(
        kind: str | None = None,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {"runs": [shape_run_row(r) for r in stores.runs.list(tenant_id, kind=kind)]}

    @app.get("/api/runs/{run_id}")
    def get_run(
        run_id: str,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        run = stores.runs.get(tenant_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        events = stores.trace.events(tenant_id, run_id)
        book = stores.books.get(tenant_id, run_id) if run.get("kind") == "paper" else None
        return shape_run(run, events, book=book)

    @app.get("/api/runs/{run_id}/book")
    def get_book(
        run_id: str,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        run = stores.runs.get(tenant_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"book": stores.books.get(tenant_id, run_id)}

    @app.get("/api/strategies")
    def list_strategies(
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return {"strategies": stores.strategies.list(tenant_id)}

    # ---- human money-path actions (shared control-plane implementation) ----------------
    @app.post("/api/strategies", status_code=201)
    def propose(
        body: ProposeBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        return _do(actions.propose_strategy, stores, ctx, stores.core, body.spec)

    @app.post("/api/runs", status_code=201)
    def create_run(
        body: CreateRunBody,
        ctx: Ctx = Depends(_ctx),
        stores: Stores = Depends(get_stores),
    ) -> dict[str, Any]:
        try:
            return actions.create_run(stores, ctx, strategy_id=body.strategy_id,
                                      kind=body.kind, range_=body.range)
        except ActionError as err:
            raise HTTPException(status_code=err.status, detail=err.detail) from err

    def _action_route(fn):
        def route(run_id: str, ctx: Ctx = Depends(_ctx),
                  stores: Stores = Depends(get_stores)) -> dict[str, Any]:
            return _do(fn, stores, ctx, run_id)
        return route

    for _name, _fn in (
        ("promote", actions.promote_run), ("activate", actions.activate_run),
        ("pause", actions.pause_run), ("resume", actions.resume_run),
        ("retire", actions.retire_run),
    ):
        app.add_api_route(f"/api/runs/{{run_id}}/{_name}", _action_route(_fn),
                          methods=["POST"], name=f"run_{_name}")

    # ---- live trace stream -------------------------------------------------------------
    @app.get("/api/runs/{run_id}/events")
    def stream_events(
        run_id: str,
        request: Request,
        tenant_id: str = Depends(require_tenant),
        stores: Stores = Depends(get_stores),
        last_event_id: str | None = Header(default=None),
    ) -> StreamingResponse:
        run = stores.runs.get(tenant_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")

        after_seq = parse_last_event_id(last_event_id)
        qp = request.query_params.get("after_seq")
        if qp is not None:
            after_seq = parse_last_event_id(qp)

        replay_only = request.query_params.get("replay_only") == "1"
        deadline = request.query_params.get("deadline")
        deadline_seconds = float(deadline) if deadline is not None else None

        stream = event_stream(
            stores.trace, tenant_id, run_id,
            after_seq=after_seq, deadline_seconds=deadline_seconds, replay_only=replay_only,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


# Module-level app for `uvicorn doomberg_rest.app:app`.
app = create_app()
