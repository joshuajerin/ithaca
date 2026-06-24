"""Read-model: shape platform rows into what the web UI needs.

Pure projection — no I/O, no eval (the v1 RCE lesson), just reshaping already-validated,
tenant-scoped store rows. Two jobs:

1. :func:`shape_run_row` — normalize a ``RunStore`` row for the UI. The store keys runs by
   ``run_id``; the UI's ``RunRow`` expects ``id``. We add ``id`` (keeping ``run_id``) so the
   list/detail/links resolve. (Without this the UI silently rendered blank rows.)

2. :func:`shape_run` — project a run + its seq-ordered trace into the three lanes the Runs
   view renders: a reasoning rail, a unified timeline spine (tool calls AND run lifecycle/
   progress/marks/fills/denials), and evidence panels keyed to a static ``panelType``. The web
   also keeps the raw ``events`` (its live reducer + replay scrubber read those); this shaped
   form is for the initial GET and any non-web consumer.
"""

from __future__ import annotations

from typing import Any

# Map a tool name to the static panel renderer key. Display-only; the UI falls back to a
# generic JSON panel for anything unmapped.
_TOOL_PANEL_TYPE: dict[str, str] = {
    "market.get_ohlcv": "ohlcv",
    "backtest.run": "backtest",
}


def shape_run_row(run: dict[str, Any]) -> dict[str, Any]:
    """Normalize a run row for the UI: expose ``id`` (= ``run_id``), keep the rest."""
    if run is None:
        return run
    return {**run, "id": run.get("run_id")}


def _tool_name(data: dict[str, Any], fallback: str | None = None) -> str | None:
    return data.get("name") or data.get("tool") or fallback


def _derive_panel_type(tool_name: str | None, data: dict[str, Any]) -> str:
    explicit = data.get("panelType")
    if isinstance(explicit, str) and explicit:
        return explicit
    if tool_name and tool_name in _TOOL_PANEL_TYPE:
        return _TOOL_PANEL_TYPE[tool_name]
    return "generic"


def shape_run(
    run: dict[str, Any], events: list[dict[str, Any]], *, book: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Project a run row + its (seq-ordered) trace into the UI read-model."""
    reasoning: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    calls_by_span: dict[str, dict[str, Any]] = {}

    for ev in events:
        etype = ev.get("type")
        data = ev.get("data") or {}
        span_id = ev.get("span_id")
        seq, ts = ev["seq"], ev["ts"]

        if etype == "reasoning":
            reasoning.append({"seq": seq, "ts": ts, "span_id": span_id,
                              "text": data.get("text", ""), "actor": ev.get("actor")})
        elif etype == "strategy_proposed":
            reasoning.append({"seq": seq, "ts": ts, "span_id": span_id,
                              "text": f"strategy proposed: {data.get('name') or data.get('strategy_id') or ''}"})
            timeline.append({"seq": seq, "ts": ts, "kind": "strategy_proposed", "data": data})
        elif etype == "tool_call":
            entry = {"seq": seq, "ts": ts, "kind": "tool", "span_id": span_id,
                     "name": _tool_name(data), "args": data.get("args"),
                     "status": "pending", "result_seq": None}
            timeline.append(entry)
            if span_id is not None:
                calls_by_span[span_id] = entry
        elif etype == "tool_result":
            call = calls_by_span.get(span_id) if span_id is not None else None
            tool_name = _tool_name(data, call.get("name") if call else None)
            if call is not None:
                call["status"] = "error" if data.get("error") else "ok"
                call["result_seq"] = seq
            evidence.append({"seq": seq, "ts": ts, "span_id": span_id, "name": tool_name,
                             "panelType": _derive_panel_type(tool_name, data),
                             "data": data.get("data") or data,
                             "provenance": data.get("provenance")})
        elif etype in (
            "run_transition", "run_progress", "job_queued", "job_leased", "job_heartbeat",
            "artifact_created", "approval_requested", "approval_decided", "order_intent",
            "order_submitted", "order_cancelled", "fill_reconciled", "provider_status",
            "trigger_fired", "denial", "error", "session_open", "session_close",
        ):
            timeline.append({"seq": seq, "ts": ts, "kind": etype, "data": data})
        elif etype in ("mark", "fill"):
            timeline.append({"seq": seq, "ts": ts, "kind": etype, "data": data})
            evidence.append({"seq": seq, "ts": ts, "span_id": span_id, "name": etype,
                             "panelType": etype, "data": data})

    shaped = shape_run_row(run)
    shaped["trace"] = {"reasoning": reasoning, "timeline": timeline, "evidence": evidence}
    shaped["events"] = events
    if book is not None:
        shaped["book"] = book
    return shaped
