import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import { reduceUpTo } from "../timeline";
import { buildWorkflowItems, promptMeta, type WorkflowItem } from "../sessionWorkflow";
import { Panel } from "../panels/registry";
import { shortId } from "../lib/format";
import type { RunRow } from "../types";

// The first glimpse: a focused, auto-playing replay of the seeded demo research
// session (agent researches NVDA -> proposes a strategy -> requests a backtest),
// with a single clear CTA to start your own session. This is what a brand-new
// Clerk user lands on instead of the dense control-plane dashboard.
const AUTO_PLAY_MS = 1100;

export function Welcome() {
  const navigate = useNavigate();
  // The seeded demo is the tenant's first succeeded research run.
  const { data: sessions, loading, error, reload } = useAsync(
    async (signal) => api.listSessions(signal),
    [],
  );
  const demo = useMemo<RunRow | null>(() => {
    const list = sessions ?? [];
    const succeeded = list.find((s) => s.kind === "research" && s.state === "succeeded");
    return succeeded ?? list.find((s) => s.kind === "research") ?? null;
  }, [sessions]);

  // First glimpse: if the tenant has no research sessions yet, seed a replayable demo
  // so the Welcome landing has something to show. Runs once, then reloads to show it.
  const seededRef = useRef(false);
  useEffect(() => {
    if (seededRef.current || loading || error) return;
    if (sessions && sessions.length === 0) {
      seededRef.current = true;
      api.seedDemoSession().then(() => reload()).catch(() => {});
    }
  }, [sessions, loading, error, reload]);

  const demoId = demo?.run_id ?? demo?.id;

  // Fetch the full run (with its shaped trace) once we know the id.
  const { data: run } = useAsync<RunRow>(
    async (signal) => (demoId ? api.getSession(demoId, signal) : Promise.resolve(null as unknown as RunRow)),
    [demoId],
  );

  const events = useMemo(() => run?.events ?? [], [run?.events]);
  const maxSeq = events.length ? events[events.length - 1].seq : 0;

  const [playSeq, setPlaySeq] = useState<number | null>(null);
  const [playing, setPlaying] = useState(true);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const playRef = useRef<number | undefined>(undefined);

  // Auto-play: advance the replay cursor one seq at a time until the end.
  useEffect(() => {
    if (!events.length) return;
    if (playSeq === null) setPlaySeq(0);
    if (!playing || playSeq === null) return;
    if (playSeq >= maxSeq) {
      setPlaying(false);
      return;
    }
    playRef.current = window.setTimeout(() => setPlaySeq((s) => (s ?? 0) + 1), AUTO_PLAY_MS);
    return () => {
      if (playRef.current !== undefined) window.clearTimeout(playRef.current);
    };
  }, [events.length, playing, playSeq, maxSeq]);

  const visibleSeq = playSeq ?? maxSeq;
  const state = useMemo(() => reduceUpTo(events, visibleSeq), [events, visibleSeq]);
  const workflow = useMemo(() => buildWorkflowItems(state, events), [state, events]);
  const meta = useMemo(() => promptMeta(events), [events]);
  const selected = workflow.find((i) => i.key === selectedKey) ?? workflow[workflow.length - 1];

  function startOwn() {
    navigate("/new-session");
  }

  return (
    <div className="page welcome-page">
      <header className="welcome-head">
        <div className="welcome-eyebrow">Welcome to Doomberg</div>
        <h1 className="welcome-title">Watch your agent think.</h1>
        <p className="welcome-lede">
          This is a replay of a real research session — an agent researching a ticker,
          screening peers, proposing a strategy, and requesting a backtest. Yours will
          stream live the moment you start one.
        </p>
      </header>

      {error ? (
        <div className="welcome-empty empty">{error}</div>
      ) : loading || !demo ? (
        <div className="welcome-empty empty">{loading ? "Loading your demo session…" : "No demo session yet."}</div>
      ) : (
        <section className="welcome-replay">
          <div className="welcome-prompt">
            <div className="prompt-label">user</div>
            <div className="prompt-text">{meta.prompt ?? "Prompt not captured"}</div>
            <div className="prompt-meta">
              <span>session {shortId(demoId)}</span>
              <span>{state.nodes.length} calls</span>
              <span>{workflow.length} steps</span>
            </div>
          </div>

          <div className="welcome-replay-body">
            <div className="welcome-workflow">
              <div className="col-head">
                <span>Workflow</span>
                <span>{Math.min(visibleSeq, maxSeq)}/{maxSeq}</span>
              </div>
              <div className="workflow-list">
                {workflow.map((item) => (
                  <WorkflowNode
                    item={item}
                    key={item.key}
                    dimmed={item.seq > visibleSeq}
                    selected={selected?.key === item.key}
                    onSelect={() => { setSelectedKey(item.key); setPlaying(false); }}
                  />
                ))}
              </div>
            </div>

            <div className="welcome-output">
              <div className="col-head">
                <span>Output</span>
                <span>{selected?.name ?? "-"}</span>
              </div>
              <div className="output-body">
                {selected ? <SelectedOutput item={selected} /> : <div className="empty">Select a step.</div>}
              </div>
            </div>
          </div>

          <div className="welcome-scrub">
            <button
              className={`btn ${playing ? "primary" : ""}`}
              onClick={() => {
                if (visibleSeq >= maxSeq) { setPlaySeq(0); setPlaying(true); }
                else setPlaying((p) => !p);
              }}
            >
              {playing ? "Pause" : visibleSeq >= maxSeq ? "Replay" : "Play"}
            </button>
            <input
              className="scrub"
              type="range"
              min={0}
              max={maxSeq}
              value={visibleSeq}
              onChange={(e) => { setPlaySeq(Number(e.target.value)); setPlaying(false); }}
            />
            <span className="page-sub">seq {visibleSeq}/{maxSeq}</span>
          </div>
        </section>
      )}

      <section className="welcome-cta">
        <h2>Start your own session</h2>
        <p>
          Point your agent at Doomberg over MCP. Its research, proposals, and backtests
          stream into a live trace just like the one above — and you stay in control of
          every promote, activate, and retire.
        </p>
        <div className="welcome-cta-actions">
          <button className="btn primary lg" onClick={startOwn}>Start a session</button>
          <Link className="btn lg" to="/agent-link">Connect your agent</Link>
          <Link className="link-btn" to="/dashboard">Go to the dashboard</Link>
        </div>
      </section>
    </div>
  );
}

function WorkflowNode({ item, dimmed, selected, onSelect }: {
  item: WorkflowItem;
  dimmed: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`wf-node ${selected ? "sel" : ""} ${dimmed ? "dim" : ""}`}
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
  const args = item.node?.call?.data
    ? ((item.node.call.data as Record<string, unknown>).args ?? item.node.call.data)
    : null;

  if (item.kind === "prompt") {
    return (
      <>
        <div className="output-title">Prompt</div>
        <pre className="pre">{item.summary}</pre>
      </>
    );
  }

  return (
    <>
      <div className="output-title">{item.kind === "tool" ? "Returned summary" : "Event payload"}</div>
      {item.node?.status === "pending" ? (
        <div className="empty">{item.name} is still running…</div>
      ) : (
        <Panel panelType={item.node?.panelType} data={item.node?.resultData ?? data} />
      )}
      {args && (
        <>
          <div className="output-title">Args</div>
          <pre className="pre">{safeJson(args)}</pre>
        </>
      )}
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
