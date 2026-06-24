#!/usr/bin/env python3
"""Executable launch gate for customer handoff.

The gate verifies the platform as a control plane rather than checking only that processes
started. Local mode opens the real platform DB, mints a scoped tenant key, and drives the
REST/MCP apps through HTTP semantics. HTTP mode points at an already deployed REST/MCP pair.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any


ALL_GATE_SCOPES = [
    "data:read",
    "strategy:author",
    "runs:write",
    "runs:cancel",
    "approvals:read",
    "approvals:decide",
    "providers:write",
    "triggers:write",
    "artifacts:read",
    "deploy:backtest",
    "deploy:paper",
]


@dataclass
class GateResult:
    name: str
    status: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"pass", "warn", "skip"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "evidence": self.evidence,
        }


class Response:
    def __init__(self, status_code: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.status_code = int(status_code)
        self.body = body
        self.headers = headers or {}

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text or "{}")


class RestClient:
    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        tenant_id: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Response:
        raise NotImplementedError


class InProcessRestClient(RestClient):
    def __init__(self, client: Any) -> None:
        self._client = client

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        tenant_id: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Response:
        headers = _headers(token=token, tenant_id=tenant_id)
        raw = self._client.request(method, path, headers=headers, json=json_body)
        return Response(raw.status_code, raw.content, dict(raw.headers))


class RemoteRestClient(RestClient):
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        tenant_id: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Response:
        url = self.base_url + (path if path.startswith("/") else f"/{path}")
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        for key, value in _headers(token=token, tenant_id=tenant_id).items():
            req.add_header(key, value)
        req.add_header("Accept", "application/json, text/event-stream")
        if json_body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return Response(resp.status, resp.read(), dict(resp.headers.items()))
        except urllib.error.HTTPError as exc:
            return Response(exc.code, exc.read(), dict(exc.headers.items()))


def _headers(*, token: str | None = None, tenant_id: str | None = None) -> dict[str, str]:
    if token:
        return {"Authorization": f"Bearer {token}"}
    if tenant_id:
        return {"X-Tenant-Id": tenant_id}
    return {}


def _pass(name: str, detail: str, **evidence: Any) -> GateResult:
    return GateResult(name, "pass", detail, evidence)


def _fail(name: str, detail: str, **evidence: Any) -> GateResult:
    return GateResult(name, "fail", detail, evidence)


def _warn(name: str, detail: str, **evidence: Any) -> GateResult:
    return GateResult(name, "warn", detail, evidence)


def _skip(name: str, detail: str, **evidence: Any) -> GateResult:
    return GateResult(name, "skip", detail, evidence)


def _expect_status(response: Response, allowed: set[int], name: str) -> GateResult | None:
    if response.status_code in allowed:
        return None
    return _fail(name, f"unexpected HTTP {response.status_code}", body=response.text[:500])


def _get_json(
    rest: RestClient,
    path: str,
    *,
    token: str | None,
    tenant_id: str | None,
    name: str,
    allowed: set[int] = {200},
) -> tuple[dict[str, Any] | None, GateResult | None]:
    response = rest.request("GET", path, token=token, tenant_id=tenant_id)
    failure = _expect_status(response, allowed, name)
    if failure is not None:
        return None, failure
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        return None, _fail(name, "response was not JSON", error=str(exc), body=response.text[:500])
    if not isinstance(body, dict):
        return None, _fail(name, "response JSON was not an object", body=body)
    return body, None


def _post_json(
    rest: RestClient,
    path: str,
    body: dict[str, Any],
    *,
    token: str | None,
    tenant_id: str | None,
    name: str,
    allowed: set[int] = {200, 201},
) -> tuple[dict[str, Any] | None, GateResult | None]:
    response = rest.request("POST", path, token=token, tenant_id=tenant_id, json_body=body)
    failure = _expect_status(response, allowed, name)
    if failure is not None:
        return None, failure
    try:
        parsed = response.json()
    except json.JSONDecodeError as exc:
        return None, _fail(name, "response was not JSON", error=str(exc), body=response.text[:500])
    if not isinstance(parsed, dict):
        return None, _fail(name, "response JSON was not an object", body=parsed)
    return parsed, None


def _check_unauthorized_rest(rest: RestClient) -> GateResult:
    response = rest.request("GET", "/api/runs", token="dmbg_test_notareal_secret")
    if response.status_code == 401:
        return _pass("rest unauthorized rejection", "invalid bearer key rejected", status=401)
    return _fail(
        "rest unauthorized rejection",
        f"expected 401 for invalid bearer key, got {response.status_code}",
        body=response.text[:500],
    )


def _check_ops(
    rest: RestClient,
    *,
    token: str | None,
    tenant_id: str | None,
    require_postgres: bool,
    require_active_worker: bool,
) -> tuple[dict[str, Any] | None, list[GateResult]]:
    body, failure = _get_json(
        rest,
        "/api/ops/status",
        token=token,
        tenant_id=tenant_id,
        name="ops status",
    )
    if failure:
        return None, [failure]
    assert body is not None
    database = (body.get("platform") or {}).get("database")
    results = [_pass("ops status", "REST ops status returned", database=database)]
    if require_postgres and database != "postgres":
        results.append(_fail("postgres requirement", "platform database is not postgres", database=database))
    else:
        results.append(_pass("database mode", f"platform database is {database}", database=database))
    leases = body.get("leases") or []
    if require_active_worker:
        active = [lease for lease in leases if lease.get("lease_name") != "launch-gate"]
        if not active:
            results.append(_fail("active worker lease", "no non-launch-gate worker lease is active"))
        else:
            results.append(_pass("active worker lease", "active worker lease found", leases=active))
    return body, results


def _check_session_and_events(
    rest: RestClient,
    *,
    token: str | None,
    tenant_id: str | None,
) -> tuple[str | None, list[GateResult]]:
    created, failure = _post_json(
        rest,
        "/api/sessions",
        {"prompt": "launch gate customer handoff smoke", "title": "launch-gate"},
        token=token,
        tenant_id=tenant_id,
        name="session create",
    )
    if failure:
        return None, [failure]
    assert created is not None
    run_id = str(created.get("id") or created.get("run_id") or "")
    if not run_id:
        return None, [_fail("session create", "created session did not include a run id", body=created)]
    results = [
        _pass(
            "session create",
            "research session opened through REST",
            run_id=run_id,
            state=created.get("state"),
            tenant_id=created.get("tenant_id"),
        )
    ]

    run, failure = _get_json(
        rest,
        f"/api/runs/{urllib.parse.quote(run_id)}",
        token=token,
        tenant_id=tenant_id,
        name="run fetch",
    )
    if failure:
        results.append(failure)
    elif run and run.get("id") == run_id and (run.get("events") or []):
        results.append(_pass("run fetch", "run read model includes events", events=len(run["events"])))
    else:
        results.append(_fail("run fetch", "run read model missing id or events", body=run))

    response = rest.request(
        "GET",
        f"/api/runs/{urllib.parse.quote(run_id)}/events?replay_only=1&deadline=0",
        token=token,
        tenant_id=tenant_id,
    )
    if response.status_code != 200:
        results.append(_fail("event replay", f"unexpected HTTP {response.status_code}", body=response.text[:500]))
    elif "session_open" not in response.text:
        results.append(_fail("event replay", "SSE replay did not include session_open", body=response.text[:500]))
    else:
        results.append(_pass("event replay", "SSE replay returned session_open", bytes=len(response.body)))

    return run_id, results


def _check_artifacts(
    rest: RestClient,
    *,
    token: str | None,
    tenant_id: str | None,
    local_stores: Any | None,
    run_id: str | None,
    require_artifact: bool,
) -> list[GateResult]:
    if local_stores is not None and run_id:
        artifact = local_stores.artifacts.create(
            tenant_id or "",
            run_id,
            kind="launch-gate",
            uri=f"memory://launch-gate/{run_id}/summary.json",
            media_type="application/json",
            bytes_=2,
            metadata={"launch_gate": True},
        )
        body, failure = _get_json(
            rest,
            f"/api/artifacts/{artifact['artifact_id']}",
            token=token,
            tenant_id=tenant_id,
            name="artifact fetch",
        )
        if failure:
            return [failure]
        if body and body.get("artifact_id") == artifact["artifact_id"]:
            return [_pass("artifact fetch", "artifact metadata fetched by id", artifact_id=artifact["artifact_id"])]
        return [_fail("artifact fetch", "artifact response did not match created artifact", body=body)]

    body, failure = _get_json(
        rest,
        "/api/artifacts",
        token=token,
        tenant_id=tenant_id,
        name="artifact list",
    )
    if failure:
        return [failure]
    artifacts = (body or {}).get("artifacts") or []
    if not artifacts:
        if require_artifact:
            return [_fail("artifact fetch", "no existing artifact was available to fetch in HTTP mode")]
        return [_warn("artifact fetch", "artifact list works, but no artifact exists to fetch in HTTP mode")]
    artifact_id = artifacts[0].get("artifact_id")
    body, failure = _get_json(
        rest,
        f"/api/artifacts/{urllib.parse.quote(str(artifact_id))}",
        token=token,
        tenant_id=tenant_id,
        name="artifact fetch",
    )
    if failure:
        return [failure]
    return [_pass("artifact fetch", "existing artifact metadata fetched by id", artifact_id=artifact_id)]


def _check_ibkr(
    rest: RestClient,
    *,
    token: str | None,
    tenant_id: str | None,
    symbol: str,
    skip: bool,
    require: bool,
) -> GateResult:
    if skip:
        return _skip("ibkr smoke", "skipped by operator flag")
    body, failure = _get_json(
        rest,
        f"/api/ops/ibkr-smoke?symbol={urllib.parse.quote(symbol)}",
        token=token,
        tenant_id=tenant_id,
        name="ibkr smoke",
    )
    if failure:
        return failure
    assert body is not None
    if body.get("ok"):
        quote = body.get("quote") or {}
        return _pass(
            "ibkr smoke",
            "connected-account quote route passed invariants",
            symbol=body.get("symbol"),
            price=quote.get("price"),
            freshness_ms=quote.get("freshness_ms"),
            latency_ms=body.get("latency_ms"),
        )
    if require:
        return _fail(
            "ibkr smoke",
            str(body.get("error") or body.get("status") or "IBKR smoke failed"),
            status=body.get("status"),
            code=body.get("code"),
            recovery_action=body.get("recovery_action"),
        )
    return _warn(
        "ibkr smoke",
        str(body.get("error") or body.get("status") or "IBKR smoke did not pass"),
        status=body.get("status"),
        code=body.get("code"),
        recovery_action=body.get("recovery_action"),
    )


def _check_mcp_unauthorized_url(mcp_url: str) -> GateResult:
    req = urllib.request.Request(
        mcp_url,
        data=json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "search_skills", "arguments": {"query": "market"}},
        }).encode("utf-8"),
        method="POST",
    )
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return _fail("mcp unauthorized rejection", f"expected 401, got HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return _pass("mcp unauthorized rejection", "unauthenticated MCP tool call rejected", status=401)
        return _fail("mcp unauthorized rejection", f"expected 401, got HTTP {exc.code}", body=exc.read().decode("utf-8", errors="replace")[:500])
    except Exception as exc:  # noqa: BLE001 - operator-facing diagnostic.
        return _fail("mcp unauthorized rejection", f"MCP request failed: {exc}")


def _check_mcp_unauthorized_local(db: Any) -> GateResult:
    from fastapi.testclient import TestClient

    from doomberg_core import Core
    from doomberg_mcp import PlatformTraceSink, Toolset, build_http_app
    from doomberg_platform import Platform

    platform = Platform(db)
    toolset = Toolset(core=Core(), sink=PlatformTraceSink(platform.trace), runs=platform.runs, platform=platform)
    app, _mcp, _ts = build_http_app(toolset=toolset, verifier=platform.auth)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers={"accept": "application/json, text/event-stream", "content-type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search_skills", "arguments": {"query": "market"}},
            },
        )
    if response.status_code == 401:
        return _pass("mcp unauthorized rejection", "unauthenticated MCP tool call rejected", status=401)
    return _fail("mcp unauthorized rejection", f"expected 401, got HTTP {response.status_code}", body=response.text[:500])


def _run_local(args: argparse.Namespace) -> list[GateResult]:
    from fastapi.testclient import TestClient

    from doomberg_platform import open_db
    from doomberg_rest import create_app

    dsn = args.db or os.environ.get("DOOMBERG_DB") or ":memory:"
    db = open_db(dsn)
    app = create_app(db)
    stores = app.state.stores
    if args.tenant_id:
        tenant_id = args.tenant_id
        if stores.auth.get_tenant(tenant_id) is None:
            db.close()
            return [_fail("tenant key", f"tenant does not exist: {tenant_id}")]
    else:
        tenant_id = stores.auth.create_tenant(f"launch-gate-{uuid.uuid4().hex[:8]}")
    token, key_id = stores.auth.mint_key(tenant_id, ALL_GATE_SCOPES)
    owner_id = f"launch-gate-{uuid.uuid4().hex[:8]}"
    stores.leases.acquire(
        "launch-gate",
        owner_id,
        ttl_seconds=120,
        metadata={"script": "scripts/launch_gate.py"},
    )
    results = [
        _pass(
            "platform migration",
            "platform DB opened and schema is ready",
            dsn="postgres" if getattr(db, "is_postgres", False) else dsn,
            database="postgres" if getattr(db, "is_postgres", False) else "sqlite",
        ),
        _pass("tenant key", "scoped launch-gate key minted", tenant_id=tenant_id, key_id=key_id),
    ]
    try:
        with TestClient(app) as client:
            rest = InProcessRestClient(client)
            results.append(_check_unauthorized_rest(rest))
            _ops, ops_results = _check_ops(
                rest,
                token=token,
                tenant_id=None,
                require_postgres=args.require_postgres,
                require_active_worker=args.require_active_worker,
            )
            results.extend(ops_results)
            run_id, session_results = _check_session_and_events(rest, token=token, tenant_id=None)
            results.extend(session_results)
            results.extend(
                _check_artifacts(
                    rest,
                    token=token,
                    tenant_id=tenant_id,
                    local_stores=stores,
                    run_id=run_id,
                    require_artifact=True,
                )
            )
            results.append(
                _check_ibkr(
                    rest,
                    token=token,
                    tenant_id=None,
                    symbol=args.ibkr_symbol,
                    skip=args.skip_ibkr,
                    require=args.require_ibkr,
                )
            )
        results.append(_check_mcp_unauthorized_local(db))
    finally:
        stores.leases.release("launch-gate", owner_id)
        db.close()
    return results


def _run_http(args: argparse.Namespace) -> list[GateResult]:
    if not args.base_url:
        return [_fail("configuration", "--base-url or DOOMBERG_REST_URL is required for HTTP mode")]
    token = args.api_key or os.environ.get("DOOMBERG_API_KEY")
    tenant_id = args.tenant_id or str(uuid.uuid4())
    rest = RemoteRestClient(args.base_url)
    auth_tenant = None if token else tenant_id
    results = [_pass("configuration", "HTTP launch gate configured", base_url=args.base_url)]
    results.append(_check_unauthorized_rest(rest))
    _ops, ops_results = _check_ops(
        rest,
        token=token,
        tenant_id=auth_tenant,
        require_postgres=args.require_postgres,
        require_active_worker=args.require_active_worker,
    )
    results.extend(ops_results)
    run_id, session_results = _check_session_and_events(rest, token=token, tenant_id=auth_tenant)
    results.extend(session_results)
    results.extend(
        _check_artifacts(
            rest,
            token=token,
            tenant_id=auth_tenant,
            local_stores=None,
            run_id=run_id,
            require_artifact=args.require_artifact,
        )
    )
    results.append(
        _check_ibkr(
            rest,
            token=token,
            tenant_id=auth_tenant,
            symbol=args.ibkr_symbol,
            skip=args.skip_ibkr,
            require=args.require_ibkr,
        )
    )
    mcp_url = args.mcp_url or os.environ.get("DOOMBERG_MCP_URL")
    if mcp_url:
        results.append(_check_mcp_unauthorized_url(mcp_url))
    elif args.require_mcp:
        results.append(_fail("mcp unauthorized rejection", "--mcp-url or DOOMBERG_MCP_URL is required"))
    else:
        results.append(_skip("mcp unauthorized rejection", "no MCP URL configured"))
    return results


def _print_results(results: list[GateResult], *, as_json: bool) -> None:
    failed = [r for r in results if r.status == "fail"]
    warned = [r for r in results if r.status == "warn"]
    summary = {
        "ok": not failed,
        "failed": len(failed),
        "warned": len(warned),
        "passed": sum(1 for r in results if r.status == "pass"),
        "skipped": sum(1 for r in results if r.status == "skip"),
        "results": [r.to_dict() for r in results],
    }
    if as_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    for result in results:
        marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}[result.status]
        print(f"{marker:4} {result.name}: {result.detail}")
    print(
        f"summary: passed={summary['passed']} warned={summary['warned']} "
        f"failed={summary['failed']} skipped={summary['skipped']}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Doomberg customer-handoff launch gates.")
    parser.add_argument(
        "--mode",
        choices=["local", "http"],
        default="http" if os.environ.get("DOOMBERG_REST_URL") else "local",
        help="local drives the in-process app against DOOMBERG_DB; http drives a deployed REST URL.",
    )
    parser.add_argument("--db", default=None, help="Platform DB DSN for local mode. Defaults to DOOMBERG_DB.")
    parser.add_argument("--base-url", default=os.environ.get("DOOMBERG_REST_URL"), help="REST base URL for HTTP mode.")
    parser.add_argument("--mcp-url", default=os.environ.get("DOOMBERG_MCP_URL"), help="MCP endpoint URL for HTTP mode.")
    parser.add_argument("--api-key", default=os.environ.get("DOOMBERG_API_KEY"), help="Bearer key for deployed REST.")
    parser.add_argument("--tenant-id", default=None, help="Tenant id for dev-header HTTP mode or local synthetic tenant.")
    parser.add_argument("--ibkr-symbol", default="AAPL", help="Symbol for the optional IBKR read-only smoke.")
    parser.add_argument("--skip-ibkr", action="store_true", help="Do not call /api/ops/ibkr-smoke.")
    parser.add_argument("--require-ibkr", action="store_true", help="Fail if the IBKR smoke does not pass.")
    parser.add_argument("--require-postgres", action="store_true", help="Fail unless ops status reports Postgres.")
    parser.add_argument("--require-active-worker", action="store_true", help="Fail unless an existing non-launch-gate worker lease is active.")
    parser.add_argument("--require-artifact", action="store_true", help="In HTTP mode, fail if no existing artifact can be fetched.")
    parser.add_argument("--require-mcp", action="store_true", help="In HTTP mode, fail if no MCP URL is configured.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results = _run_local(args) if args.mode == "local" else _run_http(args)
    _print_results(results, as_json=args.json)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
