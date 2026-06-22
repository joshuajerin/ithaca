import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { SessionRow } from "../types";
import { fmtTime, shortId, stateClass } from "../lib/format";

export function SessionsList() {
  const { data, loading, error, reload } = useAsync<SessionRow[]>((s) => api.listSessions(s), []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="page-title">Sessions</div>
          <div className="page-sub">MCP workflow history · prompts · tools · returned summaries</div>
        </div>
        <div className="toolbar compact">
          <Link to="/new-session" className="btn primary">New Session</Link>
          <button className="btn" onClick={reload}>Refresh</button>
        </div>
      </div>

      {error && <div className="banner">Failed to load sessions: {error}</div>}
      {loading && <div className="empty">Loading sessions...</div>}
      {!loading && !error && (data?.length ?? 0) === 0 && (
        <div className="empty">No research sessions yet. Start one from New Session.</div>
      )}

      {(data?.length ?? 0) > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>Session</th>
              <th>Prompt</th>
              <th>Agent</th>
              <th>State</th>
              <th>Calls</th>
              <th>Warnings</th>
              <th>Last event</th>
            </tr>
          </thead>
          <tbody>
            {data!.slice().reverse().map((row) => (
              <tr key={row.id} onClick={() => { window.location.hash = `#/sessions/${row.id}`; }}>
                <td><Link to={`/sessions/${row.id}`}>{shortId(row.id)}</Link></td>
                <td>{row.title || row.prompt || "Prompt not captured"}</td>
                <td>{row.agent || "unknown"}</td>
                <td><span className={`badge ${stateClass(row.state)}`}>{row.state}</span></td>
                <td>{row.call_count ?? 0}</td>
                <td>{row.warning_count ?? 0}</td>
                <td>{fmtTime(row.last_event_at ?? row.updated_at ?? row.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

