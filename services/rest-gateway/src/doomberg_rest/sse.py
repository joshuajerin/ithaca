"""Server-Sent Events framing + the replay-then-tail event stream.

The web UI subscribes to a run's trace over SSE. The lifecycle is:

  1. Replay: read durable events with ``seq > last_seq`` via ``TraceStore.events`` (honoring
     the ``Last-Event-ID`` header the browser resends on reconnect).
  2. Live tail: ``TraceStore.subscribe(run_id, after_seq=last_seq)`` for events that land
     after the replay snapshot.
  3. Heartbeat: emit ``: keepalive`` comment lines periodically so idle proxies don't kill
     the stream (the v1 idle-kill lesson).

Each SSE message ``id:`` is the event ``seq`` so the browser's automatic reconnect resends
it as ``Last-Event-ID`` and we resume gap-free.

The live tail blocks in the platform's in-proc pub/sub, so we run it on a worker thread and
hand frames back through a queue; the async generator can then interleave heartbeats and
honor a wall-clock deadline without blocking the event loop. Never ``except: pass`` on this
path — failures are surfaced as an ``error`` SSE frame.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

# Sentinels passed through the bridge queue from the subscribe thread.
_DONE = object()

# How long to wait for a live event before emitting a heartbeat (seconds).
HEARTBEAT_SECONDS = 15.0


def format_event(event: dict[str, Any]) -> str:
    """Render one trace event as an SSE message block (``id:``/``event:``/``data:``)."""
    seq = event["seq"]
    etype = event.get("type", "message")
    payload = json.dumps(event, default=str)
    return f"id: {seq}\nevent: {etype}\ndata: {payload}\n\n"


def keepalive_comment() -> str:
    """An SSE comment line that proxies pass through but the EventSource ignores."""
    return ": keepalive\n\n"


def parse_last_event_id(value: str | None) -> int:
    """Parse a ``Last-Event-ID`` header into an ``after_seq`` (defaults to -1 = from start)."""
    if value is None:
        return -1
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


async def event_stream(
    trace_store: Any,
    tenant_id: str,
    run_id: str,
    *,
    after_seq: int = -1,
    deadline_seconds: float | None = None,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    replay_only: bool = False,
) -> AsyncIterator[str]:
    """Yield SSE frames: replay-from-seq, then live tail with heartbeats.

    Args:
        trace_store: a :class:`doomberg_platform.TraceStore`.
        tenant_id / run_id: tenant-scoped identifiers (UUID strings).
        after_seq: replay events with ``seq > after_seq`` (from ``Last-Event-ID``).
        deadline_seconds: aggregate wall-clock budget for the whole stream; ``None`` = no
            limit (the default for a live UI tail). When set, the stream closes cleanly
            after the budget elapses.
        heartbeat_seconds: idle interval before emitting a ``: keepalive`` comment.
        replay_only: if True, emit the replay snapshot and stop (used in tests / one-shots).
    """
    loop = asyncio.get_running_loop()
    if deadline_seconds is not None:
        end_at = loop.time() + deadline_seconds
    else:
        end_at = None

    last_seq = after_seq

    # 1) Replay durable events (tenant-scoped) up to the current snapshot.
    for ev in trace_store.events(tenant_id, run_id, after_seq=after_seq):
        last_seq = int(ev["seq"])
        yield format_event(ev)

    if replay_only:
        return

    # 2) Live tail. The store's subscribe() blocks, so drive it on a thread and bridge
    #    frames through an asyncio queue. A stop flag lets us unstick the thread on close.
    queue: asyncio.Queue[Any] = asyncio.Queue()
    stop = threading.Event()

    def _pump() -> None:
        try:
            for ev in trace_store.subscribe(run_id, after_seq=last_seq):
                if stop.is_set():
                    break
                loop.call_soon_threadsafe(queue.put_nowait, ev)
        except Exception as exc:  # surface, never swallow — emit an error frame
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    worker = threading.Thread(target=_pump, name=f"sse-tail-{run_id}", daemon=True)
    worker.start()

    try:
        while True:
            if end_at is not None:
                remaining = end_at - loop.time()
                if remaining <= 0:
                    break
                timeout = min(heartbeat_seconds, remaining)
            else:
                timeout = heartbeat_seconds

            try:
                item = await asyncio.wait_for(queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                yield keepalive_comment()
                continue

            if item is _DONE:
                break
            if isinstance(item, Exception):
                err = {
                    "seq": last_seq + 1,
                    "type": "error",
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "data": {"message": str(item)},
                }
                yield format_event(err)
                break

            seq = int(item["seq"])
            if seq <= last_seq:
                continue
            last_seq = seq
            yield format_event(item)
    finally:
        stop.set()
