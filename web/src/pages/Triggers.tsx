import { Link } from "react-router-dom";
import { useState } from "react";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { TriggerDryRunResult, TriggerRow } from "../types";
import { fmtTime, shortId, stateClass } from "../lib/format";

const DEFAULT_POLICY = JSON.stringify({
  when: { event: "market.quote", universe: ["AAPL"] },
  condition: { all: [{ price: { gte: 200 } }] },
  controls: { dedupe_key: "${symbol}:price", cooldown: "15m", max_runs_per_day: 4 },
  action: { run_skill: "market.quote", mode: "analyze" },
}, null, 2);

export function Triggers() {
  const { data, loading, error, reload } = useAsync<TriggerRow[]>((s) => api.listTriggers(s), []);
  const [name, setName] = useState("price-review");
  const [policyText, setPolicyText] = useState(DEFAULT_POLICY);
  const [formError, setFormError] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState<TriggerDryRunResult | null>(null);

  function parsePolicy(): Record<string, unknown> | null {
    try {
      return JSON.parse(policyText) as Record<string, unknown>;
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
      return null;
    }
  }

  async function create() {
    setFormError(null);
    const policy = parsePolicy();
    if (!policy) return;
    await api.createTrigger(name, policy, "draft");
    reload();
  }

  async function dryRunPolicy() {
    setFormError(null);
    setDryRun(null);
    const policy = parsePolicy();
    if (!policy) return;
    setDryRun(await api.dryRunTrigger(name, policy));
  }

  async function setState(row: TriggerRow, state: string) {
    await api.setTriggerState(row.trigger_id, state);
    reload();
  }

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">Triggers</div>
        <button className="btn" onClick={reload}>Refresh</button>
      </div>

      <section className="ops-card">
        <div className="section-head"><span>New trigger</span></div>
        <div className="control-form">
          <label>Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label>Policy<textarea value={policyText} onChange={(e) => setPolicyText(e.target.value)} rows={9} /></label>
          {formError && <div className="banner">Policy error: {formError}</div>}
          {dryRun && <pre className="pre">{JSON.stringify(dryRun, null, 2)}</pre>}
          <div className="toolbar">
            <button className="btn" onClick={() => void dryRunPolicy()}>Dry run</button>
            <button className="btn primary" onClick={() => void create()}>Create draft</button>
          </div>
        </div>
      </section>

      {error && <div className="banner">Failed to load triggers: {error}</div>}
      {loading && <div className="empty">Loading triggers...</div>}
      {!loading && !error && (data?.length ?? 0) === 0 && <div className="empty">No triggers.</div>}

      {(data?.length ?? 0) > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>Trigger</th>
              <th>Name</th>
              <th>State</th>
              <th>Policy</th>
              <th>Updated</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data!.map((row) => (
              <tr key={row.trigger_id}>
                <td>{shortId(row.trigger_id)}</td>
                <td>{row.name}</td>
                <td><span className={`badge ${stateClass(row.state)}`}>{row.state}</span></td>
                <td><code className="mono json-inline">{compact(row.policy)}</code></td>
                <td>{fmtTime(row.updated_at)}</td>
                <td>
                  <div className="row-actions">
                    <button className="btn" onClick={() => void setState(row, "active")}>Activate</button>
                    <button className="btn" onClick={() => void setState(row, "paused")}>Pause</button>
                    <button className="btn" onClick={() => void setState(row, "retired")}>Retire</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="set-hint"><Link to="/approvals">Trigger-created approvals appear in Approvals.</Link></div>
    </div>
  );
}

function compact(value: unknown): string {
  const text = JSON.stringify(value);
  return text.length > 180 ? `${text.slice(0, 180)}...` : text;
}
