import { useState } from "react";
import { api, type ProviderConnectionInput } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { DatasetSnapshotRow, OpsStatus, ProviderConnectionRow } from "../types";
import { fmtTime, shortId, stateClass } from "../lib/format";

export function Providers() {
  const providers = useAsync<{ connections: ProviderConnectionRow[]; snapshots: DatasetSnapshotRow[] }>(
    (s) => api.listProviders(s),
    [],
  );
  const ops = useAsync<OpsStatus>((s) => api.getOpsStatus(s), []);
  const [provider, setProvider] = useState("doomberg-live-data");
  const [capabilities, setCapabilities] = useState("quote,bars");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    const body: ProviderConnectionInput = {
      provider,
      capabilities: capabilities.split(",").map((x) => x.trim()).filter(Boolean),
      entitlements: [{ dataset: "us_equities", entitlement_class: "doomberg_live" }],
      state: "connected",
    };
    try {
      await api.upsertProviderConnection(body);
      providers.reload();
      ops.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">Providers</div>
        <div className="toolbar compact">
          <button className="btn" onClick={providers.reload}>Refresh</button>
        </div>
      </div>

      {ops.data && (
        <div className="ops-grid">
          <Metric label="Database" value={ops.data.platform.database} />
          <Metric label="Live data" value={ops.data.live_data.engine_configured ? "configured" : "not configured"} />
          <Metric label="Paper" value={ops.data.execution.paper_enabled ? "enabled" : "paused"} state={ops.data.execution.paper_enabled ? "ok" : "warn"} />
          <Metric label="Triggers" value={`${ops.data.triggers.active}/${ops.data.triggers.total} active`} />
        </div>
      )}

      <section className="ops-card">
        <div className="section-head"><span>Provider connection</span></div>
        <div className="control-form inline">
          <label>Provider<input value={provider} onChange={(e) => setProvider(e.target.value)} /></label>
          <label>Capabilities<input value={capabilities} onChange={(e) => setCapabilities(e.target.value)} /></label>
          <button className="btn primary" onClick={() => void save()}>Save</button>
        </div>
        {error && <div className="banner">{error}</div>}
      </section>

      {providers.error && <div className="banner">Failed to load providers: {providers.error}</div>}
      {providers.loading && <div className="empty">Loading providers...</div>}

      {(providers.data?.connections.length ?? 0) > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>Connection</th>
              <th>Provider</th>
              <th>State</th>
              <th>Capabilities</th>
              <th>Credential</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {providers.data!.connections.map((row) => (
              <tr key={row.connection_id}>
                <td>{shortId(row.connection_id)}</td>
                <td>{row.provider}</td>
                <td><span className={`badge ${stateClass(row.state)}`}>{row.state}</span></td>
                <td>{row.capabilities.join(", ") || "-"}</td>
                <td>{row.credential_configured ? "configured" : "-"}</td>
                <td>{fmtTime(row.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {(providers.data?.snapshots.length ?? 0) > 0 && (
        <section className="ops-card">
          <div className="section-head"><span>Dataset snapshots</span></div>
          <table className="tbl">
            <thead>
              <tr>
                <th>Snapshot</th>
                <th>Provider</th>
                <th>Dataset</th>
                <th>Entitlement</th>
                <th>As of</th>
              </tr>
            </thead>
            <tbody>
              {providers.data!.snapshots.map((row) => (
                <tr key={row.snapshot_id}>
                  <td>{shortId(row.snapshot_id)}</td>
                  <td>{row.provider}</td>
                  <td>{row.dataset}</td>
                  <td>{row.entitlement_class}</td>
                  <td>{fmtTime(row.as_of)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value, state }: { label: string; value: string; state?: string }) {
  return (
    <div className="dash-stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-val ${state ?? ""}`}>{value}</div>
    </div>
  );
}
