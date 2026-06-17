"""Append-only trace store: gap-free seq per run_id, tenant-scoped reads, live tail.

Every event is validated against :class:`doomberg_contracts.TraceEvent` (a closed,
``extra="forbid"`` schema) before it is persisted. ``append`` assigns the gap-free seq
inside a single write transaction (single writer per run), so observers can rely on seq
as a contiguous SSE ``Last-Event-ID`` cursor.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from doomberg_contracts import TraceEvent

from .db import Db


def _uuid_str(value: Any) -> str:
    """Normalize a UUID / UUID-string to its canonical string form."""
    return str(value)


def _row_to_event(row: Any) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "seq": row["seq"],
        "ts": row["ts"],
        "type": row["type"],
        "tenant_id": row["tenant_id"],
        "session_id": row["session_id"],
        "origin_session_id": row["origin_session_id"],
        "span_id": row["span_id"],
        "parent_span_id": row["parent_span_id"],
        "actor": json.loads(row["actor"]) if row["actor"] else None,
        "data": json.loads(row["data"]),
    }


class TraceStore:
    """Append-only, gap-free-seq-per-run trace event log."""

    def __init__(self, db: Db) -> None:
        self._db = db

    def append(self, event: dict[str, Any]) -> int:
        """Validate `event`, assign a gap-free seq for its run_id, persist, return seq.

        The caller MUST NOT supply seq; it is server-assigned. A ``seq`` key in the input
        is ignored (overwritten). Validation is against the TraceEvent contract; a bad
        event raises :class:`pydantic.ValidationError` and nothing is written.
        """
        payload = dict(event)
        # seq is server-owned. Stamp a placeholder so the contract (seq >= 0) validates
        # the rest of the event; the real value is computed under the write lock below.
        payload["seq"] = 0
        model = TraceEvent.model_validate(payload)

        tenant_id = _uuid_str(model.tenant_id)
        run_id = _uuid_str(model.run_id)
        session_id = _uuid_str(model.session_id) if model.session_id else None
        origin_session_id = (
            _uuid_str(model.origin_session_id) if model.origin_session_id else None
        )
        actor_json = (
            json.dumps(model.actor.model_dump(mode="json")) if model.actor else None
        )
        data_json = json.dumps(model.data)
        ts_iso = model.ts.isoformat()
        type_str = model.type.value

        with self._db.write_lock:
            conn = self._db.conn
            with conn:
                cur = conn.execute(
                    "SELECT next_seq FROM run_seq WHERE run_id = ?", (run_id,)
                )
                row = cur.fetchone()
                seq = 0 if row is None else int(row["next_seq"])
                conn.execute(
                    "INSERT INTO trace_events "
                    "(tenant_id, run_id, seq, ts, type, session_id, origin_session_id, "
                    " span_id, parent_span_id, actor, data) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tenant_id,
                        run_id,
                        seq,
                        ts_iso,
                        type_str,
                        session_id,
                        origin_session_id,
                        model.span_id,
                        model.parent_span_id,
                        actor_json,
                        data_json,
                    ),
                )
                conn.execute(
                    "INSERT INTO run_seq (run_id, next_seq) VALUES (?, ?) "
                    "ON CONFLICT(run_id) DO UPDATE SET next_seq = ?",
                    (run_id, seq + 1, seq + 1),
                )

        # Publish the durable, normalized event for any live SSE tail.
        published = _row_to_event_from_values(
            tenant_id=tenant_id,
            run_id=run_id,
            seq=seq,
            ts=ts_iso,
            type=type_str,
            session_id=session_id,
            origin_session_id=origin_session_id,
            span_id=model.span_id,
            parent_span_id=model.parent_span_id,
            actor=json.loads(actor_json) if actor_json else None,
            data=model.data,
        )
        self._db.publish(run_id, published)
        return seq

    def events(
        self, tenant_id: str, run_id: str, after_seq: int = -1
    ) -> list[dict[str, Any]]:
        """Replay tenant-scoped events for a run with seq > after_seq, ordered by seq."""
        tenant_id = _uuid_str(tenant_id)
        run_id = _uuid_str(run_id)
        cur = self._db.conn.execute(
            "SELECT * FROM trace_events "
            "WHERE tenant_id = ? AND run_id = ? AND seq > ? "
            "ORDER BY seq ASC",
            (tenant_id, run_id, after_seq),
        )
        return [_row_to_event(r) for r in cur.fetchall()]

    def subscribe(self, run_id: str, after_seq: int = -1) -> Iterator[dict[str, Any]]:
        """Live tail for SSE: yields events as they are appended (seq > after_seq).

        In-process pub/sub locally; Postgres LISTEN/NOTIFY swaps in for prod without a
        signature change. Pair with :meth:`events` for replay-then-tail (the rest-gateway
        reads `events(..., after_seq)` first, then subscribes for the live continuation).
        """
        run_id = _uuid_str(run_id)
        return self._db.subscribe(run_id, after_seq=after_seq)


def _row_to_event_from_values(**kw: Any) -> dict[str, Any]:
    return {
        "run_id": kw["run_id"],
        "seq": kw["seq"],
        "ts": kw["ts"],
        "type": kw["type"],
        "tenant_id": kw["tenant_id"],
        "session_id": kw["session_id"],
        "origin_session_id": kw["origin_session_id"],
        "span_id": kw["span_id"],
        "parent_span_id": kw["parent_span_id"],
        "actor": kw["actor"],
        "data": kw["data"],
    }
