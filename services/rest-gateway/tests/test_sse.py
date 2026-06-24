"""SSE tests: framing, replay-from-seq, live tail, heartbeat, tenant scoping."""

from __future__ import annotations

import asyncio
import json

from doomberg_rest.sse import (
    event_stream,
    format_event,
    keepalive_comment,
    parse_last_event_id,
)

from rest_helpers import append_event, seed_run


def test_format_event_frames_id_and_type():
    frame = format_event({"seq": 7, "type": "reasoning", "data": {"text": "hi"}})
    assert frame.startswith("id: 7\n")
    assert "event: reasoning\n" in frame
    assert frame.endswith("\n\n")
    # data line is valid JSON carrying the event
    data_line = [line for line in frame.splitlines() if line.startswith("data: ")][0]
    assert json.loads(data_line[len("data: "):])["seq"] == 7


def test_keepalive_is_a_comment():
    assert keepalive_comment().startswith(": keepalive")


def test_parse_last_event_id():
    assert parse_last_event_id(None) == -1
    assert parse_last_event_id("4") == 4
    assert parse_last_event_id("garbage") == -1


def _parse_ids(text: str) -> list[int]:
    return [int(line[len("id: "):]) for line in text.splitlines() if line.startswith("id: ")]


def test_sse_streams_existing_events_for_run(client, stores, tenant_a):
    run_id = seed_run(stores, tenant_a)
    for i in range(3):
        append_event(stores, tenant_a, run_id, type="reasoning", data={"text": str(i)})

    # replay_only stops after the snapshot so the request completes deterministically.
    resp = client.get(
        f"/api/runs/{run_id}/events",
        params={"replay_only": "1"},
        headers={"X-Tenant-Id": tenant_a},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert _parse_ids(resp.text) == [0, 1, 2]


def test_sse_replay_from_seq(client, stores, tenant_a):
    run_id = seed_run(stores, tenant_a)
    for i in range(5):
        append_event(stores, tenant_a, run_id, type="reasoning", data={"text": str(i)})

    # Last-Event-ID = 1 => only events with seq > 1 (2,3,4).
    resp = client.get(
        f"/api/runs/{run_id}/events",
        params={"replay_only": "1"},
        headers={"X-Tenant-Id": tenant_a, "Last-Event-ID": "1"},
    )
    assert _parse_ids(resp.text) == [2, 3, 4]


def test_sse_requires_tenant_and_scopes(client, stores, tenant_a, tenant_b):
    run_id = seed_run(stores, tenant_a)
    # missing header
    assert client.get(f"/api/runs/{run_id}/events").status_code == 400
    # wrong tenant => 404 (no cross-tenant tail)
    resp = client.get(
        f"/api/runs/{run_id}/events",
        params={"replay_only": "1"},
        headers={"X-Tenant-Id": tenant_b},
    )
    assert resp.status_code == 404


def test_event_stream_live_tail_then_deadline(db):
    """Replay snapshot, then tail a late append, then close cleanly on the wall-clock deadline.

    Driven via ``asyncio.run`` so no async-pytest plugin is required.
    """
    import uuid
    from datetime import datetime, timezone

    from doomberg_platform import RunStore, TraceStore

    tenant = str(uuid.uuid4())
    runs = RunStore(db)
    trace = TraceStore(db)
    run_id = runs.create(tenant, "backtest", None, None)

    def _append(text: str) -> None:
        trace.append(
            {
                "run_id": run_id,
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "reasoning",
                "tenant_id": tenant,
                "data": {"text": text},
            }
        )

    _append("first")  # seq 0, part of replay

    async def _scenario() -> list[int]:
        seqs: list[int] = []
        gen = event_stream(trace, tenant, run_id, deadline_seconds=1.0)

        # First frame is the replayed seq 0.
        frame0 = await gen.__anext__()
        seqs.append(int(frame0.splitlines()[0][len("id: "):]))

        # Append a live event; the tail thread delivers it.
        _append("second")  # seq 1
        frame1 = await gen.__anext__()
        seqs.append(int(frame1.splitlines()[0][len("id: "):]))

        # Drain the rest; must terminate on the deadline (heartbeats allowed in between).
        async def _drain() -> None:
            async for _ in gen:
                pass

        await asyncio.wait_for(_drain(), timeout=5.0)
        return seqs

    seqs = asyncio.run(_scenario())
    assert seqs == [0, 1]
