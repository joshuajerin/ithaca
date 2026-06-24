"""Control plane (FastAPI) — the SINGLE writer of the money path.

The endpoint bodies are thin: they resolve the request :class:`Ctx`, call the matching
function in :mod:`doomberg_control.actions` (the one money-path implementation, shared with
the rest-gateway), and translate :class:`ActionError` into an HTTP error. All the invariants
— tenant scope, human-only money actions, declarative-spec-only, audited denials — live in
``actions`` so they hold no matter which transport invoked them.

Endpoints (all require ``X-Tenant-Id`` → :class:`Ctx`):
- ``POST /strategies``            propose a spec (validate → persist draft → trace).
- ``POST /runs``                  create a run (``backtest``|``paper``), land it ``queued``.
- ``POST /runs/{id}/cancel``      cancel a queued/running run and its worker jobs.
- ``POST /runs/{id}/promote``     HUMAN. Paper only. Compliance + risk gate, then promote.
- ``POST /runs/{id}/activate``    HUMAN. ``promoted``/``paused`` → ``live`` (scheduler ticks it).
- ``POST /runs/{id}/pause``       HUMAN. ``live`` → ``paused``.
- ``POST /runs/{id}/resume``      HUMAN. ``paused`` → ``live``.
- ``POST /runs/{id}/retire``      HUMAN. → ``retired``.
- ``GET  /runs`` / ``GET /runs/{id}``  tenant-scoped reads.
"""
from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
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
    idempotency_key: str | None = None


class CancelRunBody(BaseModel):
    reason: str | None = None


class CreateTenantBody(BaseModel):
    name: str


class MintKeyBody(BaseModel):
    scopes: list[str]


def _require_admin(x_admin_token: str | None) -> None:
    """Gate the operator-only admin endpoints behind ``DOOMBERG_ADMIN_TOKEN``.

    If the env var is unset the endpoints are INERT: any call returns 404, so they do not
    exist for tests / dev and cannot be reached without an operator deliberately enabling
    them. If set, the request must present the matching ``X-Admin-Token``.
    """
    expected = os.environ.get("DOOMBERG_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(status_code=404, detail="not found")
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="admin token required")


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
                                      kind=body.kind, range_=body.range,
                                      idempotency_key=body.idempotency_key)
        except ActionError as err:
            _raise(err)

    @app.post("/runs/{run_id}/cancel")
    def cancel_run(
        run_id: str,
        body: CancelRunBody | None = None,
        ctx: Ctx = Depends(get_ctx),
        platform: Platform = Depends(get_platform),
    ) -> dict[str, Any]:
        try:
            return actions.cancel_run(platform, ctx, run_id, reason=body.reason if body else None)
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

    # ---- admin (operator-only; inert unless DOOMBERG_ADMIN_TOKEN is set) ----------------
    @app.post("/admin/tenants", status_code=201)
    def create_tenant(
        body: CreateTenantBody,
        platform: Platform = Depends(get_platform),
        x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    ) -> dict[str, Any]:
        _require_admin(x_admin_token)
        try:
            tenant_id = platform.auth.create_tenant(body.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"tenant_id": tenant_id, "name": body.name}

    @app.post("/admin/tenants/{tenant_id}/keys", status_code=201)
    def mint_key(
        tenant_id: str,
        body: MintKeyBody,
        platform: Platform = Depends(get_platform),
        x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    ) -> dict[str, Any]:
        _require_admin(x_admin_token)
        try:
            plaintext, key_id = platform.auth.mint_key(tenant_id, body.scopes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # The plaintext is returned exactly ONCE — it is unrecoverable thereafter.
        return {"key_id": key_id, "api_key": plaintext, "scopes": body.scopes,
                "tenant_id": tenant_id}

    return app


app = create_app()
