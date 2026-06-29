import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { RunRow, SessionRow } from "../types";
import { fmtTime, stateClass } from "../lib/format";
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

function formatArgs(args: unknown): Array<{ k: string; v: string }> {
  if (args == null) return [];
  if (typeof args === "string") return [{ k: "input", v: args.slice(0, 160) }];
  if (typeof args === "object" && !Array.isArray(args)) {
    return Object.entries(args as Record<string, unknown>)
      .slice(0, 6)
      .map(([k, v]) => ({
        k,
        v: typeof v === "string" ? v.slice(0, 120) : JSON.stringify(v).slice(0, 120),
      }));
  }
  return [{ k: "args", v: JSON.stringify(args).slice(0, 160) }];
}

function formatResult(result: unknown): string {
  if (result == null) return "";
  if (typeof result === "string") return result.slice(0, 300);
  return JSON.stringify(result).slice(0, 300);
}

// ── Search icon ───────────────────────────────────────────────────────────────

function SearchIcon() {
  return (
    <svg className="searchbar-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <circle cx="6.5" cy="6.5" r="4" /><line x1="10" y1="10" x2="14" y2="14" />
    </svg>
  );
}

// ── Flow step card ─────────────────────────────────────────────────────────────

function FlowStepCard({
  step,
  index,
  onClick,
}: {
  step: SkillStep;
  index: number;
  onClick: () => void;
}) {
  const preview = formatArgs(step.args).slice(0, 2);
  return (
    <div
      className={`flow-card${step.status === "error" ? " err" : ""}`}
      onClick={onClick}
    >
      <div className="flow-card-head">
        <div className="flow-card-title">
          <span className={`flow-dot ${step.status}`} />
          <span className="flow-card-name">{step.name}</span>
        </div>
        <div className="flow-card-meta">
          <span className="flow-card-seq">#{index + 1}</span>
          <span className="flow-card-dur">
            {step.durationMs != null ? `${step.durationMs}ms` : fmtTime(step.ts)}
          </span>
        </div>
      </div>
      {preview.length > 0 && (
        <div className="flow-card-preview">
          {preview.map(({ k, v }) => (
            <span key={k} className="flow-preview-pair">
              <span className="flow-preview-key">{k}</span>
              <span className="flow-preview-val">{v}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function StepPopup({ step, index, onClose }: { step: SkillStep; index: number; onClose: () => void }) {
  const argPairs = formatArgs(step.args);
  const resultText = formatResult(step.result);

  return (
    <div className="step-popup-backdrop" onClick={onClose}>
      <div className="step-popup" onClick={(e) => e.stopPropagation()}>
        <div className="step-popup-head">
          <div className="step-popup-title">
            <span className={`flow-dot ${step.status}`} />
            <span>{step.name}</span>
          </div>
          <div className="step-popup-meta">
            <span>#{index + 1}</span>
            <span>{step.durationMs != null ? `${step.durationMs}ms` : fmtTime(step.ts)}</span>
            <button className="step-popup-close" onClick={onClose}>✕</button>
          </div>
        </div>
        <div className="step-popup-body">
          {argPairs.length > 0 && (
            <div className="flow-card-section">
              <div className="flow-section-label">args</div>
              <div className="flow-args-grid">
                {argPairs.map(({ k, v }) => (
                  <div key={k} className="flow-arg-row">
                    <span className="flow-arg-key">{k}</span>
                    <span className="flow-arg-val">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {resultText && !step.evidence && (
            <div className="flow-card-section">
              <div className="flow-section-label">result</div>
              <div className="flow-result-text">{resultText}</div>
            </div>
          )}
          {step.evidence && (
            <div className="flow-card-section">
              <div className="flow-section-label">evidence</div>
              <Panel panelType={step.evidence.panelType} data={step.evidence.data} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function SessionsList() {
  const { id: routeId } = useParams<{ id?: string }>();
  const navigate = useNavigate();

  const [query, setQuery] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(routeId ?? null);
  const [popupStep, setPopupStep] = useState<SkillStep | null>(null);

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
          <input
            className="searchbar"
            type="search"
            placeholder="Search sessions…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="topbar-right" />
      </div>

      {sessError && (
        <div className="banner" style={{ margin: "0 22px 12px" }}>
          Failed to load sessions: {sessError}
        </div>
      )}

      {/* 2-column body */}
      <div className="sessions-body-v2">

        {/* Col 1: Sessions table */}
        <div className="sessions-table-col">
          {sessLoading ? (
            <div className="empty" style={{ padding: 24 }}>Loading sessions…</div>
          ) : filtered.length === 0 ? (
            <div className="empty" style={{ padding: 24 }}>
              {q ? `No sessions match "${query}"` : "No sessions yet."}
            </div>
          ) : (
            <table className="sess-tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Time</th>
                  <th>Description</th>
                  <th className="sess-tbl-steps">Steps</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr
                    key={row.id}
                    className={selectedSessionId === row.id ? "sel" : ""}
                    onClick={() => selectSession(row.id)}
                  >
                    <td>
                      <div className="sess-tbl-name">
                        {row.title || row.prompt || "Untitled session"}
                      </div>
                    </td>
                    <td className="sess-tbl-time">
                      {fmtTime(row.last_event_at ?? row.updated_at ?? row.created_at)}
                    </td>
                    <td>
                      <div className="sess-tbl-desc">
                        <span className={`badge ${stateClass(row.state)}`}>{row.state}</span>
                        {(row.warning_count ?? 0) > 0 && (
                          <span style={{ color: "var(--warn)", fontSize: 9 }}>
                            {row.warning_count} warn
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="sess-tbl-steps">
                      <span className="sess-tbl-stepcount">{row.call_count ?? 0}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Col 3: Detailed flowchart */}
        <div className="sessions-flow">
          {!selectedSessionId ? (
            <div className="empty" style={{ padding: 28 }}>Select a session to see its step pipeline.</div>
          ) : detailLoading ? (
            <div className="empty" style={{ padding: 28 }}>Loading trace…</div>
          ) : steps.length === 0 ? (
            <div className="empty" style={{ padding: 28 }}>No steps recorded for this session.</div>
          ) : (
            <div className="flow-pipeline">
              <div className="flow-pipeline-header">
                <span>{steps.length} step{steps.length !== 1 ? "s" : ""}</span>
              </div>

              {steps.map((step, idx) => (
                <div key={step.key} className="flow-step-wrap">
                  <FlowStepCard
                    step={step}
                    index={idx}
                    onClick={() => setPopupStep(step)}
                  />
                  {idx < steps.length - 1 && (
                    <div className="flow-connector">
                      <div className="flow-connector-line" />
                      <div className="flow-connector-arrow">↓</div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {popupStep !== null && (
        <StepPopup
          step={popupStep}
          index={steps.findIndex((s) => s.key === popupStep.key)}
          onClose={() => setPopupStep(null)}
        />
      )}
    </div>
  );
}
