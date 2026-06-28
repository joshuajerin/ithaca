import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import { useRunEvents } from "../hooks/useRunEvents";
import { reduceEvents, reduceUpTo } from "../timeline";
import { buildWorkflowItems, promptMeta, type WorkflowItem } from "../sessionWorkflow";
import type { RunRow } from "../types";
import { Panel } from "../panels/registry";
import { fmtClock, shortId, stateClass } from "../lib/format";

export function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: run, reload } = useAsync<RunRow>((s) => api.getSession(id!, s), [id]);
  const { events: liveEvents, conn, error } = useRunEvents(id);
  const [replaySeq, setReplaySeq] = useState<number | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [memoryOpen, setMemoryOpen] = useState(false);

  const events = useMemo(() => {
    const bySeq = new Map<number, (typeof liveEvents)[number]>();
    for (const ev of run?.events ?? []) bySeq.set(ev.seq, ev);
    for (const ev of liveEvents) bySeq.set(ev.seq, ev);
    return Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq);
  }, [run?.events, liveEvents]);

  const maxSeq = events.length ? events[events.length - 1].seq : 0;
  const visibleEvents = useMemo(
    () => (replaySeq === null ? events : events.filter((ev) => ev.seq <= replaySeq)),
    [events, replaySeq],
  );
  const state = useMemo(
    () => (replaySeq === null ? reduceEvents(events) : reduceUpTo(events, replaySeq)),
    [events, replaySeq],
  );
  const workflow = useMemo(() => buildWorkflowItems(state, visibleEvents), [state, visibleEvents]);
  const meta = useMemo(() => promptMeta(visibleEvents), [visibleEvents]);
  const selected = workflow.find((item) => item.key === selectedKey) ?? workflow[workflow.length - 1];
  return (
    <div className="page session-page">
      <div className="page-head">
        <div>
          <div className="page-title">
            <Link to="/sessions" style={{ color: "var(--muted-dim)" }}>sessions</Link> / {shortId(id)}
          </div>
        </div>
        <div className="toolbar compact">
          {run && <span className={`badge ${stateClass(run.state)}`}>{run.state}</span>}
          <span className={`conn ${conn}`}>● {conn}</span>
          <button className="btn" onClick={reload}>Refresh</button>
          <button className="btn" onClick={() => setMemoryOpen((v) => !v)}>
            {memoryOpen ? "Hide Memory" : "Memory"}
          </button>
        </div>
      </div>

      {error && <div className="banner">Event stream error: {error}</div>}

      <div className="prompt-box">
        <div className="prompt-label">user</div>
        <div className="prompt-text">{meta.prompt ?? "No prompt."}</div>
        <div className="prompt-meta">
          <span>session {shortId(id)}</span>
          <span>{state.nodes.length} calls</span>
          <span>{state.denials.length} denials</span>
          <span>{state.errors.length} errors</span>
        </div>
      </div>

      <div className="toolbar replay-bar">
        <button className={`btn ${replaySeq === null ? "primary" : ""}`} onClick={() => setReplaySeq(null)}>
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
      </div>

      <div className={`session-grid ${memoryOpen ? "with-memory" : ""}`}>
        <section className="workflow-pane">
          <div className="col-head">
            <span>Workflow</span>
            <span>{workflow.length} nodes</span>
          </div>
          <div className="workflow-list">
            {workflow.map((item) => (
              <WorkflowNode
                item={item}
                key={item.key}
                selected={selected?.key === item.key}
                onSelect={() => setSelectedKey(item.key)}
              />
            ))}
            {workflow.length === 1 && state.nodes.length === 0 && (
              <div className="empty">No calls.</div>
            )}
          </div>
        </section>

        <section className="output-pane">
          <div className="col-head">
            <span>Output</span>
            <span>{selected?.name ?? "-"}</span>
          </div>
          <div className="output-body">
            {selected ? <SelectedOutput item={selected} /> : <div className="empty">Select a node.</div>}
          </div>
        </section>

        {memoryOpen && (
          <section className="memory-pane">
            <div className="col-head">
              <span>Session Memory</span>
              <span>{visibleEvents.length} events</span>
            </div>
            <div className="memory-list">
              {visibleEvents.map((ev) => (
                <button className="memory-row" key={ev.seq} onClick={() => setSelectedKey(`${ev.type}-${ev.seq}`)}>
                  <span>#{ev.seq}</span>
                  <span>{ev.type}</span>
                  <span>{fmtClock(ev.ts)}</span>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function WorkflowNode({ item, selected, onSelect }: { item: WorkflowItem; selected: boolean; onSelect: () => void }) {
  return (
    <button
      className={`wf-node ${selected ? "sel" : ""}`}
      style={{ marginLeft: item.depth * 18 }}
      onClick={onSelect}
    >
      <span className={`dot ${item.status}`} />
      <span className="wf-main">
        <span className="wf-name">{item.name}</span>
        <span className="wf-summary">{item.summary}</span>
      </span>
      <span className="tl-seq">#{item.seq}</span>
    </button>
  );
}

function SelectedOutput({ item }: { item: WorkflowItem }) {
  const data = item.event?.data ?? item.node?.resultData ?? {};
  const args = item.node?.call?.data ? ((item.node.call.data as Record<string, unknown>).args ?? item.node.call.data) : null;

  if (item.kind === "prompt") {
    return (
      <>
        <div className="output-title">Prompt</div>
        <pre className="pre">{item.summary}</pre>
        <RawEvent item={item} />
      </>
    );
  }

  return (
    <>
      <div className="output-title">{item.kind === "tool" ? "Returned summary" : "Event payload"}</div>
      {item.node?.status === "pending" ? (
        <div className="empty">Running.</div>
      ) : (
        <Panel panelType={item.node?.panelType} data={item.node?.resultData ?? data} />
      )}

      {args && (
        <>
          <div className="output-title">Args</div>
          <pre className="pre">{safeJson(args)}</pre>
        </>
      )}
      <RawEvent item={item} />
    </>
  );
}

function RawEvent({ item }: { item: WorkflowItem }) {
  return (
    <>
      <div className="output-title">Raw Event</div>
      <pre className="pre">{safeJson(item.event ?? item.node?.call ?? item)}</pre>
    </>
  );
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
