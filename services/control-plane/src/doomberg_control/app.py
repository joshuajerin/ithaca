"""Control plane (FastAPI) — the SINGLE writer of the money path.

The endpoint bodies are thin: they resolve the request :class:`Ctx`, call the matching
function in :mod:`doomberg_control.actions` (the one money-path implementation, shared with
the rest-gateway), and translate :class:`ActionError` into an HTTP error. All the invariants
— tenant scope, human-only money actions, declarative-spec-only, audited denials — live in
``actions`` so they hold no matter which transport invoked them.

Endpoints (all require ``X-Tenant-Id`` → :class:`Ctx`):
- ``POST /strategies``            propose a spec (validate → persist draft → trace).
- ``POST /runs``                  create a run (``backtest``|``paper``), land it ``queued``.
- ``POST /runs/{id}/promote``     HUMAN. Paper only. Compliance + risk gate, then promote.
- ``POST /runs/{id}/activate``    HUMAN. ``promoted``/``paused`` → ``live`` (scheduler ticks it).
- ``POST /runs/{id}/pause``       HUMAN. ``live`` → ``paused``.
- ``POST /runs/{id}/resume``      HUMAN. ``paused`` → ``live``.
- ``POST /runs/{id}/retire``      HUMAN. → ``retired``.
- ``GET  /runs`` / ``GET /runs/{id}``  tenant-scoped reads.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import actions
from .actions import ActionError
from .deps import Ctx, Platform, get_core, get_ctx, get_platform

__all__ = ["create_app", "app"]


# ----------------------------------------------------------------------------------------
# Request bodies
# ----------------------------------------------------------------------------------------
class ProposeBody(BaseModel):
    spec: dict[str, Any]


class CreateRunBody(BaseModel):
    strategy_id: str
    kind: Literal["backtest", "paper"]
    range: str = Field(default="1y")


def _raise(err: ActionError) -> None:
    raise HTTPException(status_code=err.status, detail=err.detail)


# ----------------------------------------------------------------------------------------
# App factory
# ----------------------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(title="doomberg-control-plane", version="0.0.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/strategies", status_code=201)
    def propose_strategy(
        body: ProposeBody,
        ctx: Ctx = Depends(get_ctx),
        platform: Platform = Depends(get_platform),
        core=Depends(get_core),
    ) -> dict[str, Any]:
        try:
            return actions.propose_strategy(platform, ctx, core, body.spec)
        except ActionError as err:
            _raise(err)

    @app.post("/runs", status_code=201)
    def create_run(
        body: CreateRunBody,
        ctx: Ctx = Depends(get_ctx),
        platform: Platform = Depends(get_platform),
    ) -> dict[str, Any]:
        try:
            return actions.create_run(platform, ctx, strategy_id=body.strategy_id,
                                      kind=body.kind, range_=body.range)
        except ActionError as err:
            _raise(err)

    @app.post("/runs/{run_id}/promote")
    def promote_run(run_id: str, ctx: Ctx = Depends(get_ctx),
                    platform: Platform = Depends(get_platform)) -> dict[str, Any]:
        try:
            return actions.promote_run(platform, ctx, run_id)
        except ActionError as err:
            _raise(err)

    @app.post("/runs/{run_id}/activate")
    def activate_run(run_id: str, ctx: Ctx = Depends(get_ctx),
                     platform: Platform = Depends(get_platform)) -> dict[str, Any]:
        try:
            return actions.activate_run(platform, ctx, run_id)
        except ActionError as err:
            _raise(err)

    @app.post("/runs/{run_id}/pause")
    def pause_run(run_id: str, ctx: Ctx = Depends(get_ctx),
                  platform: Platform = Depends(get_platform)) -> dict[str, Any]:
        try:
            return actions.pause_run(platform, ctx, run_id)
        except ActionError as err:
            _raise(err)

    @app.post("/runs/{run_id}/resume")
    def resume_run(run_id: str, ctx: Ctx = Depends(get_ctx),
                   platform: Platform = Depends(get_platform)) -> dict[str, Any]:
        try:
            return actions.resume_run(platform, ctx, run_id)
        except ActionError as err:
            _raise(err)

    @app.post("/runs/{run_id}/retire")
    def retire_run(run_id: str, ctx: Ctx = Depends(get_ctx),
                   platform: Platform = Depends(get_platform)) -> dict[str, Any]:
        try:
            return actions.retire_run(platform, ctx, run_id)
        except ActionError as err:
            _raise(err)

    # ---- reads -------------------------------------------------------------------------
    @app.get("/runs")
    def list_runs(
        kind: str | None = None,
        ctx: Ctx = Depends(get_ctx),
        platform: Platform = Depends(get_platform),
    ) -> dict[str, Any]:
        return {"runs": platform.runs.list(ctx.tenant_id, kind=kind)}

    @app.get("/runs/{run_id}")
    def get_run(
        run_id: str,
        ctx: Ctx = Depends(get_ctx),
        platform: Platform = Depends(get_platform),
    ) -> dict[str, Any]:
        run = platform.runs.get(ctx.tenant_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    return app


app = create_app()
