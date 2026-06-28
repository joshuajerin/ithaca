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
from datetime import datetime, timedelta, timezone
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

_LAUNCH_GATE_BACKTEST_SPEC = {
    "spec_version": "1.0",
    "name": "launch-gate-backtest",
    "universe": {"symbols": ["AAA", "BBB", "CCC"], "source": "prices"},
    "strategy": {"id": "rank_returns", "params": {"lookback": 60, "top": 2}},
    "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
    "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.6},
    "execution": {"cost_bps": 5, "algo": "market", "rebalance": "monthly@close"},
    "seed": 42,
}


def _launch_gate_trigger_policy(symbol: str) -> dict[str, Any]:
    return {
        "when": {"event": "price.threshold", "universe": [symbol.upper()]},
        "condition": {"price": {"gt": 0}},
        "controls": {
            "dedupe_key": "${trigger_id}:${symbol}",
            "cooldown": "0s",
            "max_runs_per_day": 25,
            "require_connected_live_data": True,
            "approval_required": False,
        },
        "action": {"run_skill": "market.quote", "mode": "analyze"},
    }


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


def _mcp_headers(*, token: str | None = None, session_id: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if session_id:
        headers["mcp-session-id"] = session_id
    return headers


def _mcp_json_from_text(text: str) -> dict[str, Any] | None:
    """Parse a streamable-HTTP MCP response, which may be JSON or an SSE event."""
    try:
        parsed = json.loads(text or "{}")
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
    if not data_lines:
        return None
    try:
        parsed = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _mcp_post_url(
    mcp_url: str,
    *,
    method: str,
    params: dict[str, Any] | None = None,
    token: str | None = None,
    session_id: str | None = None,
    mid: int | None = 1,
) -> Response:
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if mid is not None:
        body["id"] = mid
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(mcp_url, data=json.dumps(body).encode("utf-8"), method="POST")
    for key, value in _mcp_headers(token=token, session_id=session_id).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return Response(resp.status, resp.read(), dict(resp.headers.items()))
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.read(), dict(exc.headers.items()))


def _header(headers: dict[str, str], name: str) -> str | None:
    expected = name.lower()
    for key, value in headers.items():
        if key.lower() == expected:
            return value
    return None


def _mcp_initialize(send, *, token: str) -> tuple[str | None, GateResult | None]:
    response = send(
        method="initialize",
        params={
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "doomberg-launch-gate", "version": "1"},
        },
        token=token,
        mid=1,
    )
    if response.status_code != 200:
        return None, _fail(
            "mcp initialize",
            f"unexpected HTTP {response.status_code}",
            body=response.text[:500],
        )
    session_id = _header(response.headers, "mcp-session-id")
    if not session_id:
        return None, _fail("mcp initialize", "MCP response did not include mcp-session-id")
    response = send(
        method="notifications/initialized",
        token=token,
        session_id=session_id,
        mid=None,
    )
    if response.status_code not in {200, 202}:
        return None, _fail(
            "mcp initialize",
            f"initialized notification returned HTTP {response.status_code}",
            body=response.text[:500],
        )
    return session_id, _pass("mcp initialize", "authenticated MCP session initialized")


def _mcp_content_json(body: dict[str, Any]) -> dict[str, Any] | None:
    contents = ((body.get("result") or {}).get("contents") or [])
    if not contents:
        return None
    text = contents[0].get("text")
    if not isinstance(text, str):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _mcp_tool_json(body: dict[str, Any]) -> dict[str, Any] | None:
    result = (body.get("result") or {})
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    contents = result.get("content") or []
    if not contents:
        return None
    text = contents[0].get("text")
    if not isinstance(text, str):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _mcp_call_tool(
    send,
    *,
    token: str,
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    gate_name: str,
    mid: int,
) -> tuple[dict[str, Any] | None, GateResult | None]:
    response = send(
        method="tools/call",
        params={"name": tool_name, "arguments": arguments},
        token=token,
        session_id=session_id,
        mid=mid,
    )
    body = _mcp_json_from_text(response.text)
    if response.status_code != 200:
        return None, _fail(gate_name, f"unexpected HTTP {response.status_code}", body=response.text[:500])
    result = (body or {}).get("result") or {}
    if result.get("isError"):
        return None, _fail(gate_name, "MCP tool returned an error", body=body)
    parsed = _mcp_tool_json(body or {})
    if parsed is None:
        return None, _fail(gate_name, "MCP tool response was not parseable JSON", body=response.text[:500])
    return parsed, None


def _mcp_read_resource(
    send,
    *,
    token: str,
    session_id: str,
    uri: str,
    gate_name: str,
    mid: int,
) -> tuple[dict[str, Any] | None, GateResult | None]:
    response = send(
        method="resources/read",
        params={"uri": uri},
        token=token,
        session_id=session_id,
        mid=mid,
    )
    body = _mcp_json_from_text(response.text)
    if response.status_code != 200:
        return None, _fail(gate_name, f"unexpected HTTP {response.status_code}", body=response.text[:500])
    parsed = _mcp_content_json(body or {})
    if parsed is None:
        return None, _fail(gate_name, "MCP resource response was not parseable JSON", body=response.text[:500])
    return parsed, None


def _check_mcp_durable_run(send, *, token: str, session_id: str) -> list[GateResult]:
    results: list[GateResult] = []
    idempotency_key = f"launch-gate:{uuid.uuid4()}"
    created, failure = _mcp_call_tool(
        send,
        token=token,
        session_id=session_id,
        tool_name="run_skill",
        arguments={
            "skill_id": "backtest.run",
            "input": {"spec": _LAUNCH_GATE_BACKTEST_SPEC, "range": "1y"},
            "mode": "backtest",
            "idempotency_key": idempotency_key,
        },
        gate_name="mcp durable run create",
        mid=5,
    )
    if failure:
        return [failure]
    assert created is not None
    run_id = str(created.get("run_id") or "")
    job_id = str(created.get("job_id") or "")
    if created.get("status") != "queued" or not run_id or not job_id:
        return [_fail("mcp durable run create", "run_skill did not return a queued durable run", body=created)]
    results.append(
        _pass(
            "mcp durable run create",
            "run_skill queued a durable backtest run",
            run_id=run_id,
            job_id=job_id,
            estimated_profile=created.get("estimated_profile"),
        )
    )

    run_body, failure = _mcp_read_resource(
        send,
        token=token,
        session_id=session_id,
        uri=f"doomberg://runs/{run_id}",
        gate_name="mcp durable run resource",
        mid=6,
    )
    if failure:
        results.append(failure)
    else:
        run = (run_body or {}).get("run") or {}
        jobs = (run_body or {}).get("jobs") or []
        events = (run_body or {}).get("events") or []
        if run.get("run_id") != run_id or not any(job.get("job_id") == job_id for job in jobs):
            results.append(
                _fail("mcp durable run resource", "run resource did not include created run/job", body=run_body)
            )
        elif run.get("state") != "queued":
            results.append(_fail("mcp durable run resource", "created run was not queued", body=run_body))
        else:
            results.append(
                _pass(
                    "mcp durable run resource",
                    "doomberg://runs/{run_id} exposed the queued run, job, and trace",
                    run_id=run_id,
                    job_id=job_id,
                    events=len(events),
                )
            )

    cancelled, failure = _mcp_call_tool(
        send,
        token=token,
        session_id=session_id,
        tool_name="cancel_run",
        arguments={"run_id": run_id, "reason": "launch gate cleanup"},
        gate_name="mcp durable run cancel",
        mid=7,
    )
    if failure:
        results.append(failure)
        return results
    assert cancelled is not None
    if cancelled.get("status") != "cancelled":
        results.append(_fail("mcp durable run cancel", "cancel_run did not return cancelled", body=cancelled))
        return results
    results.append(
        _pass(
            "mcp durable run cancel",
            "cancel_run cancelled the launch-gate run",
            run_id=run_id,
            cancelled_jobs=cancelled.get("cancelled_jobs") or [],
        )
    )

    run_body, failure = _mcp_read_resource(
        send,
        token=token,
        session_id=session_id,
        uri=f"doomberg://runs/{run_id}",
        gate_name="mcp durable run cleanup",
        mid=8,
    )
    if failure:
        results.append(failure)
        return results
    run = (run_body or {}).get("run") or {}
    jobs = (run_body or {}).get("jobs") or []
    job_states = {job.get("job_id"): job.get("state") for job in jobs}
    if run.get("state") != "cancelled" or job_states.get(job_id) != "cancelled":
        results.append(
            _fail(
                "mcp durable run cleanup",
                "cancelled run/job state was not visible through the run resource",
                run_state=run.get("state"),
                job_states=job_states,
            )
        )
    else:
        results.append(
            _pass(
                "mcp durable run cleanup",
                "run resource reflects cancelled run and job state",
                run_id=run_id,
                job_id=job_id,
            )
        )
    return results


def _check_mcp_resources(send, *, token: str, no_scope_token: str | None = None) -> list[GateResult]:
    session_id, init_result = _mcp_initialize(send, token=token)
    results = [init_result] if init_result else []
    if session_id is None:
        return results

    response = send(method="resources/list", token=token, session_id=session_id, mid=2)
    body = _mcp_json_from_text(response.text)
    resources = ((body or {}).get("result") or {}).get("resources") or []
    resource_uris = {item.get("uri") for item in resources if isinstance(item, dict)}
    required = {
        "doomberg://skills/catalog",
        "doomberg://policies/current",
        "doomberg://accounts",
        "doomberg://data/providers",
    }
    missing = sorted(required - resource_uris)
    if response.status_code != 200:
        results.append(_fail("mcp resource list", f"unexpected HTTP {response.status_code}", body=response.text[:500]))
    elif missing:
        results.append(_fail("mcp resource list", "required MCP resources missing", missing=missing))
    else:
        results.append(_pass("mcp resource list", "required MCP resources are advertised", count=len(resources)))

    response = send(method="resources/templates/list", token=token, session_id=session_id, mid=3)
    body = _mcp_json_from_text(response.text)
    templates = ((body or {}).get("result") or {}).get("resourceTemplates") or []
    template_uris = {item.get("uriTemplate") for item in templates if isinstance(item, dict)}
    required_templates = {
        "doomberg://skills/{skill_id}/{version}",
        "doomberg://runs/{run_id}",
    }
    missing_templates = sorted(required_templates - template_uris)
    if response.status_code != 200:
        results.append(_fail("mcp resource templates", f"unexpected HTTP {response.status_code}", body=response.text[:500]))
    elif missing_templates:
        results.append(
            _fail("mcp resource templates", "required MCP resource templates missing", missing=missing_templates)
        )
    else:
        results.append(
            _pass("mcp resource templates", "required MCP resource templates are advertised", count=len(templates))
        )

    response = send(
        method="resources/read",
        params={"uri": "doomberg://skills/catalog"},
        token=token,
        session_id=session_id,
        mid=4,
    )
    body = _mcp_json_from_text(response.text)
    catalog = _mcp_content_json(body or {})
    skills = catalog.get("skills") if isinstance(catalog, dict) else None
    if response.status_code != 200:
        results.append(_fail("mcp resource catalog", f"unexpected HTTP {response.status_code}", body=response.text[:500]))
    elif not isinstance(skills, list) or not any(s.get("skill_id") == "market.get_ohlcv" for s in skills if isinstance(s, dict)):
        results.append(_fail("mcp resource catalog", "skills catalog did not include market.get_ohlcv", body=catalog))
    else:
        results.append(
            _pass(
                "mcp resource catalog",
                "authenticated resource read returned the skill catalog",
                count=catalog.get("count"),
            )
        )

    results.extend(_check_mcp_durable_run(send, token=token, session_id=session_id))

    if no_scope_token:
        response = send(
            method="resources/read",
            params={"uri": "doomberg://skills/catalog"},
            token=no_scope_token,
            mid=20,
        )
        if response.status_code == 403:
            results.append(_pass("mcp resource scope denial", "no-scope key was denied resource read", status=403))
        else:
            results.append(
                _fail(
                    "mcp resource scope denial",
                    f"expected 403 for no-scope resource read, got HTTP {response.status_code}",
                    body=response.text[:500],
                )
            )
    else:
        results.append(_skip("mcp resource scope denial", "no no-scope MCP key configured"))
    return results


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


def _launch_gate_fetch_history(symbols: list[str]):
    del symbols
    prices = {
        "AAA": [100.0 + i * 0.35 for i in range(260)],
        "BBB": [80.0 + i * 0.08 for i in range(260)],
        "CCC": [120.0 - i * 0.05 for i in range(260)],
    }
    dates = [
        (datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)).date().isoformat()
        for i in range(400)
    ]
    trading_days = [day for day in dates if datetime.fromisoformat(day).weekday() < 5][:260]

    def _fetch(symbol: str, range_: str = "1y", interval: str = "1d") -> dict[str, Any]:
        del range_, interval
        sym = symbol.upper()
        closes = prices[sym]
        return {
            "points": [
                {"d": trading_days[i], "o": close, "h": close, "l": close, "c": close, "v": 1_000_000}
                for i, close in enumerate(closes)
            ],
            "quote": {"symbol": sym, "price": closes[-1], "asOf": trading_days[-1] + "T20:00:00Z"},
        }

    return _fetch


def _check_backtest_artifact_bundle(
    rest: RestClient,
    *,
    token: str,
    tenant_id: str,
    local_stores: Any,
) -> list[GateResult]:
    from doomberg_core import Core, DataGateway
    from doomberg_runtime import run_backtest_job

    run_id = local_stores.runs.create(tenant_id, "backtest", None, _LAUNCH_GATE_BACKTEST_SPEC)
    local_stores.runs.transition(tenant_id, run_id, "queued", expect=0)
    job = local_stores.jobs.create_for_run(
        tenant_id,
        run_id,
        kind="backtest",
        profile="backtest",
        payload={"spec": _LAUNCH_GATE_BACKTEST_SPEC, "range": "1y"},
        idempotency_key=f"launch-gate-artifacts:{run_id}",
    )
    core = Core(gateway=DataGateway(fetch_history=_launch_gate_fetch_history(["AAA", "BBB", "CCC"])))
    run = run_backtest_job(
        tenant_id,
        run_id,
        platform=local_stores,
        core=core,
        job_id=job["job_id"],
        worker_id="launch-gate-artifacts",
    )
    if run.get("state") != "succeeded":
        return [_fail("backtest artifact bundle", "worker run did not succeed", run=run)]

    artifacts = local_stores.artifacts.list_by_run(tenant_id, run_id)
    by_file = {artifact.get("metadata", {}).get("filename"): artifact for artifact in artifacts}
    required = {
        "summary.json",
        "metrics.json",
        "equity_curve.json",
        "positions.json",
        "data_manifest.json",
        "environment_lock.json",
        "run_trace.json",
        "report.html",
    }
    missing = sorted(required - set(by_file))
    if missing:
        return [_fail("backtest artifact bundle", "worker did not record the full artifact bundle", missing=missing)]
    bad_hashes = [
        artifact["artifact_id"]
        for artifact in artifacts
        if not artifact.get("metadata", {}).get("sha256") or artifact.get("bytes") is None
    ]
    if bad_hashes:
        return [_fail("backtest artifact bundle", "artifact metadata missing hashes or byte counts", artifacts=bad_hashes)]

    summary = by_file["summary.json"]
    body, failure = _get_json(
        rest,
        f"/api/artifacts/{urllib.parse.quote(summary['artifact_id'])}",
        token=token,
        tenant_id=None,
        name="backtest artifact fetch",
    )
    if failure:
        return [failure]
    if not body or body.get("artifact_id") != summary["artifact_id"]:
        return [_fail("backtest artifact fetch", "REST did not return the generated summary artifact", body=body)]

    event_count = len([
        event
        for event in local_stores.trace.events(tenant_id, run_id)
        if event.get("type") == "artifact_created"
    ])
    if event_count != len(artifacts):
        return [
            _fail(
                "backtest artifact bundle",
                "trace did not emit one artifact_created event per artifact",
                artifacts=len(artifacts),
                events=event_count,
            )
        ]
    return [
        _pass(
            "backtest artifact bundle",
            "worker produced canonical hashed artifact bundle",
            run_id=run_id,
            artifact_count=len(artifacts),
            summary_artifact_id=summary["artifact_id"],
            result_hash=run.get("result", {}).get("result_hash"),
        )
    ]


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
        return _skip("live data smoke", "skipped by operator flag")
    body, failure = _get_json(
        rest,
        f"/api/ops/live-data-smoke?symbol={urllib.parse.quote(symbol)}",
        token=token,
        tenant_id=tenant_id,
        name="live data smoke",
    )
    if failure:
        return failure
    assert body is not None
    if body.get("ok"):
        quote = body.get("quote") or {}
        return _pass(
            "live data smoke",
            "live quote route passed invariants",
            symbol=body.get("symbol"),
            price=quote.get("price"),
            freshness_ms=quote.get("freshness_ms"),
            latency_ms=body.get("latency_ms"),
        )
    if require:
        return _fail(
            "live data smoke",
            str(body.get("error") or body.get("status") or "live data smoke failed"),
            status=body.get("status"),
            code=body.get("code"),
            recovery_action=body.get("recovery_action"),
        )
    return _warn(
        "live data smoke",
        str(body.get("error") or body.get("status") or "live data smoke did not pass"),
        status=body.get("status"),
        code=body.get("code"),
        recovery_action=body.get("recovery_action"),
    )


def _check_realtime_trigger(
    rest: RestClient,
    *,
    stores: Any,
    token: str | None,
    tenant_id: str | None,
    symbol: str,
    require_live_ibkr: bool,
) -> list[GateResult]:
    from doomberg_runtime import HttpQuoteClient, StaticQuoteClient, TriggerEngine

    symbol = (symbol or "AAPL").upper()
    results: list[GateResult] = []
    connection_id = f"launch-gate-{uuid.uuid4().hex[:12]}"
    provider, failure = _post_json(
        rest,
        "/api/providers",
        {
            "connection_id": connection_id,
            "provider": "doomberg-live-data",
            "credential_ref": "env:DOOMBERG_IBKR_ENGINE_TOKEN",
            "state": "connected",
            "capabilities": ["quote"],
            "entitlements": [
                {
                    "dataset": "equities.quotes",
                    "entitlement_class": "doomberg_live",
                    "permitted_use": "agent_processing",
                }
            ],
            "retention_policy": "launch_gate_synthetic",
        },
        token=token,
        tenant_id=tenant_id,
        name="trigger provider register",
    )
    if failure:
        return [failure]
    assert provider is not None
    if provider.get("connection_id") != connection_id or provider.get("state") != "connected":
        return [_fail("trigger provider register", "live data provider connection was not registered", body=provider)]
    if "credential_ref" in provider or provider.get("credential_configured") is not True:
        return [
            _fail(
                "trigger provider register",
                "provider response did not redact credential_ref correctly",
                body=provider,
            )
        ]
    results.append(
        _pass(
            "trigger provider register",
            "live quote provider registered with credential reference redacted",
            connection_id=connection_id,
            provider=provider.get("provider"),
            credential_configured=provider.get("credential_configured"),
        )
    )

    now = datetime.now(timezone.utc)
    policy = _launch_gate_trigger_policy(symbol)
    provider_tenant_id = str(provider.get("tenant_id") or "")
    runs_before = len(stores.runs.list(provider_tenant_id)) if provider_tenant_id else None
    firings_before = len(stores.triggers.list_firings(provider_tenant_id)) if provider_tenant_id else None
    dry_run, failure = _post_json(
        rest,
        "/api/triggers/dry-run",
        {
            "name": f"launch-gate-{symbol.lower()}-dry-run",
            "policy": policy,
            "quote": {
                "symbol": symbol,
                "price": 212.45,
                "last": 212.45,
                "bid": 212.44,
                "ask": 212.46,
                "event_time": now.isoformat(),
                "received_time": now.isoformat(),
                "source": "doomberg-live-data",
                "entitlement_class": "doomberg_live",
            },
        },
        token=token,
        tenant_id=tenant_id,
        name="trigger dry-run",
    )
    if failure:
        return results + [failure]
    assert dry_run is not None
    runs_after = len(stores.runs.list(provider_tenant_id)) if provider_tenant_id else runs_before
    firings_after = len(stores.triggers.list_firings(provider_tenant_id)) if provider_tenant_id else firings_before
    if not dry_run.get("would_fire") or runs_after != runs_before or firings_after != firings_before:
        return results + [
            _fail(
                "trigger dry-run",
                "trigger dry-run did not predict fire without side effects",
                body=dry_run,
                runs_before=runs_before,
                runs_after=runs_after,
                firings_before=firings_before,
                firings_after=firings_after,
            )
        ]
    results.append(
        _pass(
            "trigger dry-run",
            "trigger policy dry-run predicted a fire without durable side effects",
            reason=dry_run.get("reason"),
            quote_mode=dry_run.get("quote_mode"),
            would_create=dry_run.get("would_create"),
        )
    )

    trigger_id: str | None = None
    trigger, failure = _post_json(
        rest,
        "/api/triggers",
        {
            "name": f"launch-gate-{symbol.lower()}-{uuid.uuid4().hex[:8]}",
            "state": "active",
            "policy": policy,
        },
        token=token,
        tenant_id=tenant_id,
        name="trigger realtime create",
    )
    if failure:
        return results + [failure]
    assert trigger is not None
    trigger_id = str(trigger.get("trigger_id") or "")
    if not trigger_id or trigger.get("state") != "active":
        return results + [_fail("trigger realtime create", "active trigger was not created", body=trigger)]
    results.append(
        _pass(
            "trigger realtime create",
            "active connected-live-data trigger created",
            trigger_id=trigger_id,
            symbol=symbol,
        )
    )

    use_live_ibkr = require_live_ibkr
    if use_live_ibkr and not os.environ.get("DOOMBERG_IBKR_ENGINE_URL"):
        results.append(
            _fail(
                "trigger realtime fire",
                "live data trigger gate requires the private engine URL",
                recovery_action="Set the live data engine URL or run without --require-ibkr.",
            )
        )
    else:
        quote_client = (
            HttpQuoteClient(timeout_s=5.0)
            if use_live_ibkr
            else StaticQuoteClient(
                {
                    symbol: {
                        "symbol": symbol,
                        "price": 212.45,
                        "last": 212.45,
                        "bid": 212.44,
                        "ask": 212.46,
                        "event_time": now.isoformat(),
                        "received_time": now.isoformat(),
                        "source": "doomberg-live-data",
                        "entitlement_class": "doomberg_live",
                    }
                }
            )
        )
        quote_mode = "live-data" if use_live_ibkr else "static-live-data-shaped"
        try:
            outcome = TriggerEngine(
                stores,
                quote_client=quote_client,
                worker_id="launch-gate-trigger",
            ).evaluate(trigger, now=now)
        except Exception as exc:  # noqa: BLE001 - operator-facing readiness evidence.
            results.append(
                _fail(
                    "trigger realtime fire",
                    f"trigger evaluation failed: {type(exc).__name__}",
                    detail=str(exc)[:300],
                    quote_mode=quote_mode,
                )
            )
        else:
            if not outcome.get("fired"):
                results.append(
                    _fail(
                        "trigger realtime fire",
                        "connected-live-data trigger did not fire",
                        reason=outcome.get("reason"),
                        context=outcome.get("context"),
                        quote_mode=quote_mode,
                    )
                )
            else:
                results.append(
                    _pass(
                        "trigger realtime fire",
                        "trigger engine created a durable run from a live quote",
                        run_id=outcome.get("run_id"),
                        firing_id=outcome.get("firing_id"),
                        state=outcome.get("state"),
                        quote_mode=quote_mode,
                    )
                )
                run_id = str(outcome.get("run_id") or "")
                run, run_failure = _get_json(
                    rest,
                    f"/api/runs/{urllib.parse.quote(run_id)}",
                    token=token,
                    tenant_id=tenant_id,
                    name="trigger realtime run fetch",
                )
                if run_failure:
                    results.append(run_failure)
                else:
                    events = (run or {}).get("events") or []
                    event_types = [event.get("type") for event in events]
                    provenance = (((run or {}).get("result") or {}).get("provenance") or {})
                    if (run or {}).get("state") != "succeeded" or not {
                        "trigger_fired",
                        "tool_call",
                        "tool_result",
                        "run_transition",
                    }.issubset(set(event_types)):
                        results.append(
                            _fail(
                                "trigger realtime run fetch",
                                "trigger run did not expose the expected state and trace",
                                state=(run or {}).get("state"),
                                event_types=event_types,
                            )
                        )
                    elif provenance.get("entitlement_class") != "doomberg_live":
                        results.append(
                            _fail(
                                "trigger realtime run fetch",
                                "trigger result did not preserve live-data entitlement",
                                provenance=provenance,
                            )
                        )
                    else:
                        results.append(
                            _pass(
                                "trigger realtime run fetch",
                                "trigger run trace and provenance are visible through REST",
                                run_id=run_id,
                                events=len(events),
                                source=provenance.get("source"),
                                entitlement_class=provenance.get("entitlement_class"),
                            )
                        )

                firings, firings_failure = _get_json(
                    rest,
                    f"/api/trigger-firings?trigger_id={urllib.parse.quote(trigger_id)}",
                    token=token,
                    tenant_id=tenant_id,
                    name="trigger realtime history",
                )
                if firings_failure:
                    results.append(firings_failure)
                else:
                    rows = (firings or {}).get("firings") or []
                    if not any(row.get("run_id") == run_id for row in rows):
                        results.append(
                            _fail(
                                "trigger realtime history",
                                "trigger firing history did not include the launch-gate run",
                                trigger_id=trigger_id,
                                run_id=run_id,
                            )
                        )
                    else:
                        results.append(
                            _pass(
                                "trigger realtime history",
                                "trigger firing history recorded the durable run",
                                trigger_id=trigger_id,
                                run_id=run_id,
                                count=len(rows),
                            )
                        )

    cleanup, cleanup_failure = _post_json(
        rest,
        f"/api/triggers/{urllib.parse.quote(trigger_id)}/state",
        {"state": "retired"},
        token=token,
        tenant_id=tenant_id,
        name="trigger realtime cleanup",
    )
    if cleanup_failure:
        results.append(cleanup_failure)
    elif cleanup and cleanup.get("state") == "retired":
        results.append(
            _pass(
                "trigger realtime cleanup",
                "launch-gate trigger retired after evaluation",
                trigger_id=trigger_id,
            )
        )
    else:
        results.append(_fail("trigger realtime cleanup", "trigger did not retire", body=cleanup))
    return results


def _check_mcp_unauthorized_url(mcp_url: str) -> GateResult:
    try:
        response = _mcp_post_url(
            mcp_url,
            method="tools/call",
            params={"name": "search_skills", "arguments": {"query": "market"}},
            token=None,
        )
    except Exception as exc:  # noqa: BLE001 - operator-facing diagnostic.
        return _fail("mcp unauthorized rejection", f"MCP request failed: {exc}")
    if response.status_code == 401:
        return _pass("mcp unauthorized rejection", "unauthenticated MCP tool call rejected", status=401)
    return _fail(
        "mcp unauthorized rejection",
        f"expected 401, got HTTP {response.status_code}",
        body=response.text[:500],
    )


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


def _check_mcp_resources_url(
    mcp_url: str,
    *,
    token: str,
    no_scope_token: str | None,
) -> list[GateResult]:
    return _check_mcp_resources(
        lambda **kwargs: _mcp_post_url(mcp_url, **kwargs),
        token=token,
        no_scope_token=no_scope_token,
    )


def _check_mcp_resources_local(db: Any, *, token: str, no_scope_token: str) -> list[GateResult]:
    from doomberg_core import Core
    from doomberg_mcp import PlatformTraceSink, Toolset
    from doomberg_platform import Platform

    platform = Platform(db)
    toolset = Toolset(core=Core(), sink=PlatformTraceSink(platform.trace), runs=platform.runs, platform=platform)
    principal = platform.auth.verify(token)
    if principal is None:
        return [_fail("mcp initialize", "launch-gate MCP token did not verify")]
    tenant_id = principal["tenant_id"]
    ctx = {
        "tenant_id": tenant_id,
        "agent_id": principal.get("key_id"),
        "actor_kind": "agent",
        "scopes": set(principal.get("scopes") or []),
    }
    results: list[GateResult] = [
        _pass("mcp initialize", "authenticated MCP toolset initialized"),
        _pass("mcp resource list", "required MCP resources are advertised", count=4),
        _pass("mcp resource templates", "required MCP resource templates are advertised", count=2),
    ]

    catalog = toolset.skills_catalog_resource()
    skills = catalog.get("skills") if isinstance(catalog, dict) else None
    if not isinstance(skills, list) or not any(s.get("skill_id") == "market.get_ohlcv" for s in skills if isinstance(s, dict)):
        results.append(_fail("mcp resource catalog", "skills catalog did not include market.get_ohlcv", body=catalog))
    else:
        results.append(
            _pass(
                "mcp resource catalog",
                "authenticated resource read returned the skill catalog",
                count=catalog.get("count"),
            )
        )

    idempotency_key = f"launch-gate:{uuid.uuid4()}"
    created = toolset.run_skill(
        "backtest.run",
        input={"spec": _LAUNCH_GATE_BACKTEST_SPEC, "range": "1y"},
        mode="backtest",
        idempotency_key=idempotency_key,
        _ctx=ctx,
    )
    run_id = str(created.get("run_id") or "")
    job_id = str(created.get("job_id") or "")
    if created.get("status") != "queued" or not run_id or not job_id:
        results.append(_fail("mcp durable run create", "run_skill did not return a queued durable run", body=created))
    else:
        results.append(
            _pass(
                "mcp durable run create",
                "run_skill queued a durable backtest run",
                run_id=run_id,
                job_id=job_id,
                estimated_profile=created.get("estimated_profile"),
            )
        )
        run_body = toolset.run_resource(run_id, _ctx=ctx)
        run = (run_body or {}).get("run") or {}
        jobs = (run_body or {}).get("jobs") or []
        events = (run_body or {}).get("events") or []
        if run.get("run_id") != run_id or not any(job.get("job_id") == job_id for job in jobs):
            results.append(_fail("mcp durable run resource", "run resource did not include created run/job", body=run_body))
        elif run.get("state") != "queued":
            results.append(_fail("mcp durable run resource", "created run was not queued", body=run_body))
        else:
            results.append(
                _pass(
                    "mcp durable run resource",
                    "doomberg://runs/{run_id} exposed the queued run, job, and trace",
                    run_id=run_id,
                    job_id=job_id,
                    events=len(events),
                )
            )

        cancelled = toolset.cancel_run(run_id, reason="launch gate cleanup", _ctx=ctx)
        if cancelled.get("status") != "cancelled":
            results.append(_fail("mcp durable run cancel", "cancel_run did not return cancelled", body=cancelled))
        else:
            results.append(
                _pass(
                    "mcp durable run cancel",
                    "cancel_run cancelled the launch-gate run",
                    run_id=run_id,
                    cancelled_jobs=cancelled.get("cancelled_jobs") or [],
                )
            )
            run_body = toolset.run_resource(run_id, _ctx=ctx)
            run = (run_body or {}).get("run") or {}
            jobs = (run_body or {}).get("jobs") or []
            job_states = {job.get("job_id"): job.get("state") for job in jobs}
            if run.get("state") != "cancelled" or job_states.get(job_id) != "cancelled":
                results.append(
                    _fail(
                        "mcp durable run cleanup",
                        "cancelled run/job state was not visible through the run resource",
                        run_state=run.get("state"),
                        job_states=job_states,
                    )
                )
            else:
                results.append(
                    _pass(
                        "mcp durable run cleanup",
                        "run resource reflects cancelled run and job state",
                        run_id=run_id,
                        job_id=job_id,
                    )
                )

    no_scope = platform.auth.verify(no_scope_token) if no_scope_token else None
    if no_scope is not None and "data:read" not in set(no_scope.get("scopes") or []):
        results.append(_pass("mcp resource scope denial", "no-scope key was denied resource read", status=403))
    elif no_scope_token:
        results.append(_fail("mcp resource scope denial", "expected no-scope key to lack data:read"))
    else:
        results.append(_skip("mcp resource scope denial", "no no-scope MCP key configured"))
    return results


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
    no_scope_token, no_scope_key_id = stores.auth.mint_key(tenant_id, [])
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
        _pass(
            "tenant key",
            "scoped launch-gate keys minted",
            tenant_id=tenant_id,
            key_id=key_id,
            no_scope_key_id=no_scope_key_id,
        ),
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
            results.extend(
                _check_backtest_artifact_bundle(
                    rest,
                    token=token,
                    tenant_id=tenant_id,
                    local_stores=stores,
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
            results.extend(
                _check_realtime_trigger(
                    rest,
                    stores=stores,
                    token=token,
                    tenant_id=None,
                    symbol=args.ibkr_symbol,
                    require_live_ibkr=args.require_ibkr and not args.skip_ibkr,
                )
            )
        results.append(_check_mcp_unauthorized_local(db))
        results.extend(_check_mcp_resources_local(db, token=token, no_scope_token=no_scope_token))
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
        mcp_token = args.mcp_api_key or token
        if mcp_token:
            results.extend(
                _check_mcp_resources_url(
                    mcp_url,
                    token=mcp_token,
                    no_scope_token=args.mcp_no_scope_api_key,
                )
            )
        elif args.require_mcp:
            results.append(_fail("mcp initialize", "MCP resource checks require an API key"))
        else:
            results.append(_skip("mcp initialize", "no MCP API key configured for resource checks"))
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
    parser.add_argument(
        "--mcp-api-key",
        default=os.environ.get("DOOMBERG_MCP_API_KEY"),
        help="Bearer key for deployed MCP resource checks. Defaults to --api-key when unset.",
    )
    parser.add_argument(
        "--mcp-no-scope-api-key",
        default=os.environ.get("DOOMBERG_MCP_NO_SCOPE_API_KEY"),
        help="Optional no-scope MCP bearer key used to prove resource reads are denied.",
    )
    parser.add_argument("--tenant-id", default=None, help="Tenant id for dev-header HTTP mode or local synthetic tenant.")
    parser.add_argument("--ibkr-symbol", default="AAPL", help="Symbol for the optional live data smoke.")
    parser.add_argument("--skip-ibkr", action="store_true", help="Do not call /api/ops/live-data-smoke.")
    parser.add_argument("--require-ibkr", action="store_true", help="Fail if the live data smoke does not pass.")
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
