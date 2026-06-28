import { useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import { useRunEvents } from "../hooks/useRunEvents";
import { reduceEvents, reduceUpTo, type TimelineNode } from "../timeline";
import type { RunRow } from "../types";
import { Panel } from "../panels/registry";
import { fmtClock, fmtTime, shortId, stateClass } from "../lib/format";

export function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: run, reload } = useAsync<RunRow>((s) => api.getRun(id!, s), [id]);
  const { events, conn, error } = useRunEvents(id);

  const reloadAll = () => {
    reload();
  };

  // Replay scrubber: when set, render state as-of that seq; otherwise follow live.
  const [replaySeq, setReplaySeq] = useState<number | null>(null);
  const [reasonOpen, setReasonOpen] = useState(true);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const maxSeq = events.length ? events[events.length - 1].seq : 0;
  const state = useMemo(
    () => (replaySeq === null ? reduceEvents(events) : reduceUpTo(events, replaySeq)),
    [events, replaySeq],
  );

  const selected: TimelineNode | undefined =
    state.nodes.find((n) => n.key === selectedKey) ?? state.nodes[state.nodes.length - 1];

  const reasoningEmpty = state.reasoning.length === 0;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="page-title">
            <Link to="/runs" style={{ color: "var(--muted-dim)" }}>
              runs
            </Link>{" "}
            / {shortId(id)}
          </div>
          <div className="page-sub">
            {run ? (
              <>
                {run.kind} · <span className={`badge ${stateClass(run.state)}`}>{run.state}</span> · strategy{" "}
                {shortId(run.strategy_id)} · {fmtTime(run.created_at)}
              </>
            ) : (
              "loading run…"
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`conn ${conn}`}>● {conn}</span>
          <button className="btn" onClick={reloadAll}>
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="banner">Event stream error: {error}</div>}
      {state.denials.length > 0 && (
        <div className="banner">
          {state.denials.length} denied action{state.denials.length > 1 ? "s" : ""} on the audited path — see the timeline.
        </div>
      )}

      {/* Replay scrubber over the fetched events */}
      <div className="toolbar">
        <button
          className={`btn ${replaySeq === null ? "primary" : ""}`}
          onClick={() => setReplaySeq(null)}
        >
          Live
        </button>
        <input
          className="scrub"
          style={{ flex: 1 }}
          type="range"
          min={0}
          max={maxSeq}
          value={replaySeq ?? maxSeq}
          onChange={(e) => setReplaySeq(Number(e.target.value))}
        />
        <span className="page-sub">
          seq {replaySeq ?? maxSeq} / {maxSeq}
        </span>
      </div>

      <div className={`run-grid ${reasoningEmpty && !reasonOpen ? "no-reason" : ""}`}>
        {/* Column 1: reasoning rail (collapsible, often empty for BYO agents) */}
        <div className="col">
          <div className="col-head">
            <span>Reasoning</span>
            <button
              className="btn"
              style={{ padding: "1px 6px" }}
              onClick={() => setReasonOpen((o) => !o)}
            >
              {reasonOpen ? "hide" : "show"}
            </button>
          </div>
          {reasonOpen && (
            <div className="col-body">
              {reasoningEmpty ? (
                <div className="empty">No reasoning emitted (typical for BYO agents).</div>
              ) : (
                state.reasoning.map((r) => (
                  <div className="reason-entry" key={r.seq}>
                    <span style={{ color: "var(--muted-dim)", fontSize: 9 }}>{fmtClock(r.ts)} </span>
                    {r.text}
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Column 2: tool-call timeline (the spine) */}
        <div className="col">
          <div className="col-head">
            <span>Timeline</span>
            <span>{state.nodes.length} calls</span>
          </div>
          <div className="col-body">
            {state.nodes.length === 0 ? (
              <div className="empty">No tool calls yet.</div>
            ) : (
              state.nodes.map((n) => (
                <div
                  key={n.key}
                  className={`tl-node ${selected?.key === n.key ? "sel" : ""}`}
                  onClick={() => setSelectedKey(n.key)}
                >
                  <div className="tl-row">
                    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className={`dot ${n.status}`} />
                      <span className="tl-name">{n.name}</span>
                    </span>
                    <span className="tl-seq">#{n.seq}</span>
                  </div>
                  {n.call?.data && Object.keys(n.call.data).length > 1 && (
                    <div style={{ color: "var(--muted-dim)", fontSize: 9, marginTop: 4 }}>
                      {argsPreview(n.call.data)}
                    </div>
                  )}
                </div>
              ))
            )}
            {(state.progress.length > 0 || state.transitions.length > 0) && (
              <div style={{ marginTop: 10 }}>
                {state.transitions.map((t) => (
                  <div key={`t${t.seq}`} className="kv" style={{ marginBottom: 3 }}>
                    <span className="k">#{t.seq} transition</span> {t.from} → {t.to}
                  </div>
                ))}
                {state.progress.slice(-3).map((p) => (
                  <div key={`p${p.seq}`} className="kv" style={{ color: "var(--muted-dim)" }}>
                    #{p.seq} progress {p.pct != null ? `${Math.round(p.pct)}%` : ""} {p.message ?? ""}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Column 3: evidence panels (static registry, no eval) */}
        <div className="col">
          <div className="col-head">
            <span>Evidence</span>
            <span>{selected?.panelType ?? "—"}</span>
          </div>
          <div className="col-body">
            {!selected ? (
              <div className="empty">Select a tool call to inspect its result.</div>
            ) : selected.status === "pending" ? (
              <div className="empty">{selected.name} is still running…</div>
            ) : selected.status === "denied" ? (
              <>
                <div className="banner">Denied: {String((selected.result?.data as Record<string, unknown>)?.reason ?? "refused by gate")}</div>
                <Panel panelType={selected.panelType} data={selected.result?.data} />
              </>
            ) : selected.status === "error" ? (
              <>
                <div className="banner">Error: {String((selected.result?.data as Record<string, unknown>)?.message ?? "tool error")}</div>
                <Panel panelType={selected.panelType} data={selected.resultData} />
              </>
            ) : (
              <Panel panelType={selected.panelType} data={selected.resultData} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function argsPreview(data: Record<string, unknown>): string {
  const args = (data.args ?? data) as Record<string, unknown>;
  const s = JSON.stringify(args);
  return s.length > 90 ? `${s.slice(0, 90)}…` : s;
}
