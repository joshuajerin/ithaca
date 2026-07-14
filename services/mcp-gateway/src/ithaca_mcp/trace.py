"""Trace emission — every MCP tool call becomes an append-only TraceEvent.

Because Ithaca owns the MCP server, we capture the agent's activity with zero agent
cooperation: each call opens a span and emits tool_call + tool_result events. ``seq`` is
gap-free per ``run_id`` (single writer per run). Events conform to the frozen TraceEvent
contract. The default sink is in-memory; the REST gateway / control plane swap in a durable
store (SQLite locally, Postgres in prod) behind the same protocol.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Protocol

from ithaca_contracts import TraceEvent


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TraceSink(Protocol):
    def emit(self, event: dict) -> None: ...


class InMemoryTrace:
    """Default sink: keeps a per-run, gap-free event log. Thread-safe."""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._seq: dict[str, int] = {}
        self._lock = threading.Lock()

    def _next_seq(self, run_id: str) -> int:
        n = self._seq.get(run_id, 0)
        self._seq[run_id] = n + 1
        return n

    def emit(self, event: dict) -> None:
        with self._lock:
            event = dict(event)
            event.setdefault("seq", self._next_seq(event["run_id"]))
            event.setdefault("ts", _now())
            # Validate against the contract so a malformed event fails loud, here, not downstream.
            TraceEvent.model_validate(event)
            self._events.append(event)

    def events(self, run_id: str | None = None) -> list[dict]:
        with self._lock:
            if run_id is None:
                return list(self._events)
            return [e for e in self._events if e["run_id"] == run_id]


class PlatformTraceSink:
    """Adapts a platform ``TraceStore`` (``.append``) to the :class:`TraceSink` protocol.

    Lets the MCP server persist a BYO agent's research trace into the shared system-of-record
    (SQLite locally, Postgres in prod) so the observability UI can replay it. The store is the
    single seq authority — it assigns the gap-free per-run ``seq`` and validates against the
    closed contract — so we drop any seq the in-memory tracer might have set.

    Duck-typed: anything exposing ``append(event) -> int`` works (no hard dependency on the
    platform package), which keeps this importable in unit tests with a fake store.
    """

    def __init__(self, store: object) -> None:
        self._store = store

    def emit(self, event: dict) -> None:
        ev = dict(event)
        ev.pop("seq", None)  # store assigns the authoritative gap-free seq
        self._store.append(ev)  # type: ignore[attr-defined]


class Tracer:
    """Builds + emits contract-shaped events for one run/session/actor."""

    def __init__(self, sink: TraceSink, *, run_id: str, tenant_id: str,
                 session_id: str | None = None, actor_id: str | None = None) -> None:
        self.sink = sink
        self.run_id = run_id
        self.tenant_id = tenant_id
        self.session_id = session_id or run_id
        self.actor_id = actor_id

    def _base(self, type_: str, data: dict, span_id: str | None, parent: str | None) -> dict:
        return {
            "run_id": self.run_id,
            "ts": _now(),
            "type": type_,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "origin_session_id": self.session_id,
            "span_id": span_id,
            "parent_span_id": parent,
            "actor": {"kind": "agent", "id": self.actor_id} if self.actor_id else None,
            "data": data,
        }

    def tool_call(self, tool: str, args: dict) -> str:
        span_id = uuid.uuid4().hex[:12]
        # ``name`` is the canonical key the read-model + web timeline pair on; ``tool`` is
        # kept as an alias for any older reader.
        self.sink.emit(self._base("tool_call", {"name": tool, "tool": tool, "args": args}, span_id, None))
        return span_id

    def tool_result(self, tool: str, span_id: str, summary: dict) -> None:
        self.sink.emit(self._base(
            "tool_result", {"name": tool, "tool": tool, "summary": summary, "data": summary},
            span_id, span_id))

    def event(self, type_: str, data: dict) -> None:
        self.sink.emit(self._base(type_, data, None, None))
