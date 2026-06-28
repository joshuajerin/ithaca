from __future__ import annotations

import os
from typing import Any

from doomberg_core.providers import PUBLIC_DATA_SOURCE, IbkrQuoteInvariantError, normalize_quote, public_quote
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from .client_portal import ClientPortalError, ClientPortalGateway


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _gateway() -> ClientPortalGateway:
    return ClientPortalGateway()


def _require_engine_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("DOOMBERG_IBKR_ENGINE_TOKEN")
    if not expected:
        return
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len(prefix):]
    if token != expected:
        raise HTTPException(status_code=403, detail="invalid bearer token")


def create_app() -> FastAPI:
    service = FastAPI(title="Doomberg Live Data Engine", version="0.0.0")

    @service.get("/healthz")
    def healthz() -> dict[str, Any]:
        health = _gateway().health()
        if not health.get("ok"):
            raise HTTPException(status_code=503, detail=health)
        return {"ok": True, "service": "doomberg-live-data-engine", "gateway": health}

    @service.get("/auth/status", dependencies=[Depends(_require_engine_token)])
    def auth_status() -> dict[str, Any]:
        try:
            return _gateway().auth_status()
        except ClientPortalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @service.get("/quote", dependencies=[Depends(_require_engine_token)])
    def quote(symbol: str = Query(..., min_length=1)) -> dict[str, Any]:
        try:
            raw = _gateway().quote(symbol)
            normalized = normalize_quote(raw, symbol=symbol, source=PUBLIC_DATA_SOURCE)
        except IbkrQuoteInvariantError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ClientPortalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"data": {"quote": public_quote(normalized)}}

    @service.get("/history", dependencies=[Depends(_require_engine_token)])
    def history(
        symbol: str = Query(..., min_length=1),
        period: str = "1d",
        bar: str = "5min",
    ) -> dict[str, Any]:
        try:
            return _gateway().history(symbol, period=period, bar=bar)
        except ClientPortalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @service.get("/news", dependencies=[Depends(_require_engine_token)])
    def news(
        ticker: str | None = None,
        symbol: str | None = None,
        limit: int = Query(default=10, ge=1, le=50),
    ) -> dict[str, Any]:
        try:
            return _gateway().news(ticker=ticker or symbol, limit=limit)
        except ClientPortalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @service.get("/scanner", dependencies=[Depends(_require_engine_token)])
    def scanner(scan_type: str = "MOST_ACTIVE", limit: int = Query(default=25, ge=1, le=100)) -> dict[str, Any]:
        try:
            return _gateway().scanner(scan_type=scan_type, limit=limit)
        except ClientPortalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @service.get("/accounts", dependencies=[Depends(_require_engine_token)])
    def accounts() -> dict[str, Any]:
        try:
            return _gateway().accounts()
        except ClientPortalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @service.get("/positions", dependencies=[Depends(_require_engine_token)])
    def positions(account: str | None = None) -> dict[str, Any]:
        try:
            return _gateway().positions(account=account)
        except ClientPortalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @service.get("/orders", dependencies=[Depends(_require_engine_token)])
    def orders(account: str | None = None) -> dict[str, Any]:
        try:
            return _gateway().orders(account=account)
        except ClientPortalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @service.post("/orders", dependencies=[Depends(_require_engine_token)])
    def submit_order(_payload: dict[str, Any]) -> dict[str, Any]:
        raise HTTPException(
            status_code=403,
            detail="order submission is disabled; this deployment is data-only",
        )

    return service


app = create_app()
