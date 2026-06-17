"""REST read-endpoint tests: tenant scoping, read-model shaping, error paths."""

from __future__ import annotations

from helpers import append_event, seed_run, seed_strategy


def test_runs_require_tenant_header(client):
    resp = client.get("/api/runs")
    assert resp.status_code == 400
    assert "X-Tenant-Id" in resp.json()["detail"]


def test_list_runs_is_tenant_scoped(client, stores, tenant_a, tenant_b):
    a_run = seed_run(stores, tenant_a, kind="backtest")
    seed_run(stores, tenant_b, kind="backtest")

    resp = client.get("/api/runs", headers={"X-Tenant-Id": tenant_a})
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert [r["run_id"] for r in runs] == [a_run]
    assert all(r["tenant_id"] == tenant_a for r in runs)
    # The UI keys off `id`; the read-model normalizes run_id -> id.
    assert runs[0]["id"] == a_run


def test_list_runs_filter_by_kind(client, stores, tenant_a):
    bt = seed_run(stores, tenant_a, kind="backtest")
    seed_run(stores, tenant_a, kind="paper")

    resp = client.get(
        "/api/runs", params={"kind": "backtest"}, headers={"X-Tenant-Id": tenant_a}
    )
    assert [r["run_id"] for r in resp.json()["runs"]] == [bt]


def test_get_run_other_tenant_is_404(client, stores, tenant_a, tenant_b):
    run_id = seed_run(stores, tenant_a)
    resp = client.get(f"/api/runs/{run_id}", headers={"X-Tenant-Id": tenant_b})
    assert resp.status_code == 404


def test_get_run_shapes_three_column_trace(client, stores, tenant_a):
    run_id = seed_run(stores, tenant_a)
    append_event(stores, tenant_a, run_id, type="reasoning", data={"text": "thinking"})
    append_event(
        stores,
        tenant_a,
        run_id,
        type="tool_call",
        span_id="s1",
        data={"name": "market.get_ohlcv", "args": {"symbol": "AAPL"}},
    )
    append_event(
        stores,
        tenant_a,
        run_id,
        type="tool_result",
        span_id="s1",
        data={"name": "market.get_ohlcv", "rows": 3},
    )

    resp = client.get(f"/api/runs/{run_id}", headers={"X-Tenant-Id": tenant_a})
    assert resp.status_code == 200
    body = resp.json()

    # Run fields are top-level (with an `id` alias the UI relies on) + a shaped trace.
    assert body["id"] == run_id
    assert body["run_id"] == run_id
    trace = body["trace"]
    assert len(trace["reasoning"]) == 1
    assert trace["reasoning"][0]["text"] == "thinking"

    assert len(trace["timeline"]) == 1
    call = trace["timeline"][0]
    assert call["name"] == "market.get_ohlcv"
    assert call["status"] == "ok"
    assert call["result_seq"] is not None

    assert len(trace["evidence"]) == 1
    ev = trace["evidence"][0]
    assert ev["panelType"] == "ohlcv"  # derived from tool name

    # The flat seq-ordered stream is preserved for the SSE cursor.
    assert [e["seq"] for e in body["events"]] == [0, 1, 2]


def test_evidence_honors_explicit_panel_type(client, stores, tenant_a):
    run_id = seed_run(stores, tenant_a)
    append_event(
        stores,
        tenant_a,
        run_id,
        type="tool_result",
        span_id="x",
        data={"name": "custom.thing", "panelType": "myPanel"},
    )
    body = client.get(f"/api/runs/{run_id}", headers={"X-Tenant-Id": tenant_a}).json()
    assert body["trace"]["evidence"][0]["panelType"] == "myPanel"


def test_tool_result_error_marks_call_status(client, stores, tenant_a):
    run_id = seed_run(stores, tenant_a)
    append_event(stores, tenant_a, run_id, type="tool_call", span_id="s1",
                 data={"name": "backtest.run"})
    append_event(stores, tenant_a, run_id, type="tool_result", span_id="s1",
                 data={"name": "backtest.run", "error": "boom"})
    body = client.get(f"/api/runs/{run_id}", headers={"X-Tenant-Id": tenant_a}).json()
    assert body["trace"]["timeline"][0]["status"] == "error"


def test_list_strategies_is_tenant_scoped(client, stores, tenant_a, tenant_b):
    seed_strategy(stores, tenant_a, "alpha")
    seed_strategy(stores, tenant_b, "beta")

    resp = client.get("/api/strategies", headers={"X-Tenant-Id": tenant_a})
    assert resp.status_code == 200
    strategies = resp.json()["strategies"]
    assert [s["name"] for s in strategies] == ["alpha"]
    assert all(s["tenant_id"] == tenant_a for s in strategies)


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}
