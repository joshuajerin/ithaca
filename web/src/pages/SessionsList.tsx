import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { RunRow, SessionRow } from "../types";
import { fmtTime, shortId, stateClass } from "../lib/format";
import { Panel } from "../panels/registry";

// ── Trace helpers ─────────────────────────────────────────────────────────────

interface SkillStep {
  key: string;
  name: string;
  status: "ok" | "error" | "pending";
  seq: number;
  ts: string;
  args?: unknown;
  result?: unknown;
  evidence?: { panelType?: string; data?: unknown };
  durationMs?: number;
}

function extractSteps(run: RunRow | null): SkillStep[] {
  if (!run) return [];
  const events = run.events ?? [];
  const steps: SkillStep[] = [];
  for (const ev of events) {
    if (ev.type === "tool_call" || ev.type === "mcp_call" || ev.type === "skill_call") {
      const d = (ev.data ?? {}) as Record<string, unknown>;
      steps.push({
        key: `${ev.seq}`,
        name: String(d["tool"] ?? d["skill"] ?? d["name"] ?? ev.type),
        status: "ok",
        seq: ev.seq,
        ts: ev.ts,
        args: d["args"] ?? d["input"],
        result: d["result"],
        evidence: d["evidence"] as SkillStep["evidence"],
        durationMs: typeof d["duration_ms"] === "number" ? d["duration_ms"] : undefined,
      });
    } else if (ev.type === "error") {
      const d = (ev.data ?? {}) as Record<string, unknown>;
      steps.push({
        key: `${ev.seq}-err`,
        name: "error",
        status: "error",
        seq: ev.seq,
        ts: ev.ts,
        result: d["message"] ?? d["error"],
      });
    }
  }
  // Also look at trace.timeline if events is empty
  if (steps.length === 0 && run.trace) {
    const trace = run.trace as Record<string, unknown>;
    const timeline = Array.isArray(trace["timeline"]) ? (trace["timeline"] as Record<string, unknown>[]) : [];
    for (const node of timeline) {
      steps.push({
        key: String(node["seq"] ?? node["id"] ?? Math.random()),
        name: String(node["tool"] ?? node["name"] ?? node["skill"] ?? "step"),
        status: node["status"] === "error" ? "error" : "ok",
        seq: typeof node["seq"] === "number" ? node["seq"] : 0,
        ts: String(node["ts"] ?? node["created_at"] ?? ""),
        args: node["args"] ?? node["input"],
        result: node["result"],
        evidence: node["evidence"] as SkillStep["evidence"],
        durationMs: typeof node["duration_ms"] === "number" ? node["duration_ms"] : undefined,
      });
    }
  }
  return steps;
}

function stepDotColor(status: SkillStep["status"]): string {
  if (status === "ok") return "var(--pos)";
  if (status === "error") return "var(--neg)";
  return "var(--warn)";
}

// ── Search icon ───────────────────────────────────────────────────────────────

function SearchIcon() {
  return (
    <svg className="searchbar-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <circle cx="6.5" cy="6.5" r="4" /><line x1="10" y1="10" x2="14" y2="14" />
    </svg>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function SessionsList() {
  const { id: routeId } = useParams<{ id?: string }>();
  const navigate = useNavigate();

  const [query, setQuery] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(routeId ?? null);
  const [selectedStepKey, setSelectedStepKey] = useState<string | null>(null);

  const { data: sessions, loading: sessLoading, error: sessError, reload } =
    useAsync<SessionRow[]>((s) => api.listSessions(s), []);

  const { data: sessionDetail, loading: detailLoading } =
    useAsync<RunRow | null>(
      async (s) => {
        if (!selectedSessionId) return null;
        return api.getSession(selectedSessionId, s);
      },
      [selectedSessionId],
    );

  const q = query.toLowerCase().trim();
  const filtered = (sessions ?? [])
    .slice()
    .reverse()
    .filter((row) =>
      !q ||
      (row.title ?? row.prompt ?? "").toLowerCase().includes(q) ||
      (row.agent ?? "").toLowerCase().includes(q) ||
      row.id.toLowerCase().includes(q),
    );

  const steps = extractSteps(sessionDetail);
  const selectedStep = steps.find((s) => s.key === selectedStepKey) ?? null;

  function selectSession(id: string) {
    setSelectedSessionId(id);
    setSelectedStepKey(null);
    navigate(`/sessions/${id}`, { replace: true });
  }

  return (
    <div className="page sessions-screen" style={{ padding: 0 }}>
      {/* Topbar */}
      <div className="topbar">
        <div className="topbar-left">
          <div className="topbar-title">Sessions</div>
        </div>
        <div className="searchbar-wrap">
          <SearchIcon />
          <input className="searchbar" type="search" placeholder="Search something..." value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="topbar-right">
          <button className="btn" onClick={reload}>Refresh</button>
        </div>
      </div>

      {sessError && <div className="banner" style={{ margin: "0 22px 12px" }}>Failed to load sessions: {sessError}</div>}

      {/* Two-column body */}
      <div className="sessions-body" style={{ flex: 1, minHeight: 0 }}>
        {/* Left: session list */}
        <div className="sessions-left">
          {sessLoading && <div className="empty">Loading sessions…</div>}
          {!sessLoading && filtered.length === 0 && (
            <div className="empty">{q ? `No sessions match "${query}"` : "No sessions yet."}</div>
          )}
          {filtered.map((row) => (
            <div
              key={row.id}
              className={`session-item ${selectedSessionId === row.id ? "sel" : ""}`}
              onClick={() => selectSession(row.id)}
            >
              <div className="session-item-title">{row.title || row.prompt || "Untitled session"}</div>
              <div className="session-item-meta">
                <span className={`badge ${stateClass(row.state)}`} style={{ marginRight: 6 }}>{row.state}</span>
                {shortId(row.id)} · {row.agent ?? "agent"} · {row.call_count ?? 0} calls
                {(row.warning_count ?? 0) > 0 && <span style={{ color: "var(--warn)", marginLeft: 6 }}>{row.warning_count} warn</span>}
              </div>
              <div className="session-item-meta" style={{ marginTop: 2, color: "var(--muted-dim)" }}>
                {fmtTime(row.last_event_at ?? row.updated_at ?? row.created_at)}
              </div>
            </div>
          ))}
        </div>

        {/* Right: skill pipeline and selected step detail */}
        <div className="sessions-right">
          {!selectedSessionId ? (
            <div className="empty" style={{ padding: 24 }}>Select a session to see its skill pipeline.</div>
          ) : detailLoading ? (
            <div className="empty" style={{ padding: 24 }}>Loading trace…</div>
          ) : steps.length === 0 ? (
            <div className="empty" style={{ padding: 24 }}>No skill steps recorded for this session.</div>
          ) : (
            <div className="skill-pipeline">
              <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted-dim)", marginBottom: 10 }}>
                {steps.length} step{steps.length !== 1 ? "s" : ""} · {sessionDetail?.state ?? ""}
              </div>
              {steps.map((step, idx) => (
                <div key={step.key}>
                  <div
                    className={`skill-step${selectedStepKey === step.key ? " sel" : ""}`}
                    onClick={() => setSelectedStepKey(step.key === selectedStepKey ? null : step.key)}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "space-between" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: stepDotColor(step.status), display: "inline-block", flexShrink: 0 }} />
                        <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--fg)", fontSize: 11 }}>{step.name}</span>
                      </div>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted-dim)" }}>
                        {step.durationMs != null ? `${step.durationMs}ms` : fmtTime(step.ts)}
                      </span>
                    </div>
                    {step.args != null && (
                      <div style={{ marginTop: 4, fontSize: 10, color: "var(--muted)", fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {typeof step.args === "string" ? step.args : JSON.stringify(step.args).slice(0, 80)}
                      </div>
                    )}
                  </div>
                  {idx < steps.length - 1 && <div className="skill-connector" />}
                </div>
              ))}
            </div>
          )}

          {selectedSessionId && !detailLoading && steps.length > 0 && (
            <div className="step-detail" role="complementary" aria-label="Step detail">
              {selectedStep ? (
                <>
                  <div className="step-detail-head">
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--fg)" }}>{selectedStep.name}</div>
                      <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                        seq {selectedStep.seq} · {fmtTime(selectedStep.ts)}
                        {selectedStep.durationMs != null ? ` · ${selectedStep.durationMs}ms` : ""}
                      </div>
                    </div>
                  </div>

                  <div style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 16 }}>
                    {selectedStep.args != null && (
                      <section>
                        <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted-dim)", marginBottom: 6 }}>Arguments</div>
                        <pre className="pre">{typeof selectedStep.args === "string" ? selectedStep.args : JSON.stringify(selectedStep.args, null, 2)}</pre>
                      </section>
                    )}

                    {selectedStep.result != null && !selectedStep.evidence && (
                      <section>
                        <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted-dim)", marginBottom: 6 }}>Result</div>
                        <pre className="pre">{typeof selectedStep.result === "string" ? selectedStep.result : JSON.stringify(selectedStep.result, null, 2)}</pre>
                      </section>
                    )}

                    {selectedStep.evidence && (
                      <section>
                        <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted-dim)", marginBottom: 8 }}>Evidence</div>
                        <Panel panelType={selectedStep.evidence.panelType} data={selectedStep.evidence.data} />
                      </section>
                    )}
                  </div>
                </>
              ) : (
                <div className="empty" style={{ padding: 24 }}>Select a skill step to inspect its result.</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
