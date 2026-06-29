import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { ApprovalRow } from "../types";
import { fmtTime, shortId, stateClass } from "../lib/format";

export function Approvals() {
  const { data, loading, error, reload } = useAsync<ApprovalRow[]>((s) => api.listApprovals(s), []);

  async function decide(row: ApprovalRow, decision: "approved" | "denied") {
    const reason = window.prompt(`${decision} reason`, decision === "approved" ? "paper approved" : "not approved") ?? "";
    await api.decideApproval(row.approval_id, decision, reason);
    reload();
  }

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">Approvals</div>
        <button className="btn" onClick={reload}>Refresh</button>
      </div>

      {error && <div className="banner">Failed to load approvals: {error}</div>}
      {loading && <div className="empty">Loading approvals...</div>}
      {!loading && !error && (data?.length ?? 0) === 0 && <div className="empty">No approvals.</div>}

      {(data?.length ?? 0) > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>Approval</th>
              <th>Kind</th>
              <th>State</th>
              <th>Run</th>
              <th>Request</th>
              <th>Decision</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data!.map((row) => (
              <tr key={row.approval_id}>
                <td>{shortId(row.approval_id)}</td>
                <td>{row.kind}</td>
                <td><span className={`badge ${stateClass(row.state)}`}>{row.state}</span></td>
                <td><Link to={`/runs/${row.run_id}`}>{shortId(row.run_id)}</Link></td>
                <td><code className="mono json-inline">{compact(row.request)}</code></td>
                <td><code className="mono json-inline">{row.decision ? compact(row.decision) : "-"}</code></td>
                <td>{fmtTime(row.created_at)}</td>
                <td>
                  {row.state === "pending" && (
                    <div className="row-actions">
                      <button className="btn primary" onClick={() => void decide(row, "approved")}>Approve</button>
                      <button className="btn" onClick={() => void decide(row, "denied")}>Deny</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function compact(value: unknown): string {
  const text = JSON.stringify(value);
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
}
