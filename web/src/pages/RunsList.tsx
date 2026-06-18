import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { RunRow } from "../types";
import { fmtTime, shortId, stateClass } from "../lib/format";

export function RunsList() {
  const { data, loading, error, reload } = useAsync<RunRow[]>((s) => api.listRuns(undefined, s), []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="page-title">Runs</div>
          <div className="page-sub">tenant {shortId(api.tenantId)} · the agent trace centerpiece</div>
        </div>
        <button className="btn" onClick={reload}>
          Refresh
        </button>
      </div>

      {error && <div className="banner">Failed to load runs: {error}</div>}
      {loading && <div className="empty">Loading runs…</div>}
      {!loading && !error && (data?.length ?? 0) === 0 && (
        <div className="empty">No runs yet. Propose a strategy and start a run via the control plane.</div>
      )}

      {(data?.length ?? 0) > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>Run</th>
              <th>Kind</th>
              <th>State</th>
              <th>Strategy</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {data!.map((r) => (
              <tr key={r.id} onClick={() => (window.location.hash = `#/runs/${r.id}`)}>
                <td>
                  <Link to={`/runs/${r.id}`}>{shortId(r.id)}</Link>
                </td>
                <td>{r.kind}</td>
                <td>
                  <span className={`badge ${stateClass(r.state)}`}>{r.state}</span>
                </td>
                <td>{shortId(r.strategy_id)}</td>
                <td>{fmtTime(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
