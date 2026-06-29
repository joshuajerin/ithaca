import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { ArtifactRow } from "../types";
import { fmtTime, shortId } from "../lib/format";

export function Artifacts() {
  const { data, loading, error, reload } = useAsync<ArtifactRow[]>((s) => api.listArtifacts(s), []);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">Artifacts</div>
        <button className="btn" onClick={reload}>Refresh</button>
      </div>

      {error && <div className="banner">Failed to load artifacts: {error}</div>}
      {loading && <div className="empty">Loading artifacts...</div>}
      {!loading && !error && (data?.length ?? 0) === 0 && <div className="empty">No artifacts.</div>}

      {(data?.length ?? 0) > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>Artifact</th>
              <th>Kind</th>
              <th>Run</th>
              <th>Bytes</th>
              <th>URI</th>
              <th>Metadata</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {data!.map((row) => (
              <tr key={row.artifact_id}>
                <td>{shortId(row.artifact_id)}</td>
                <td>{row.kind}</td>
                <td><Link to={`/runs/${row.run_id}`}>{shortId(row.run_id)}</Link></td>
                <td>{row.bytes ?? "-"}</td>
                <td><code className="mono uri-cell">{row.uri}</code></td>
                <td><code className="mono json-inline">{compact(row.metadata)}</code></td>
                <td>{fmtTime(row.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function compact(value: unknown): string {
  const text = JSON.stringify(value ?? {});
  return text.length > 120 ? `${text.slice(0, 120)}...` : text;
}
