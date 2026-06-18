import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { StrategyRow } from "../types";
import { fmtTime, shortId } from "../lib/format";

// Ideas = proposed strategies (immutable versioned specs). Display-only; proposing happens
// agent-side through the control plane, never from this observability surface.
export function Ideas() {
  const { data, loading, error } = useAsync<StrategyRow[]>((s) => api.listStrategies(s), []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="page-title">Ideas</div>
          <div className="page-sub">proposed strategy specs (StrategyStore)</div>
        </div>
      </div>

      {error && <div className="banner">Failed to load: {error}</div>}
      {loading && <div className="empty">Loading ideas…</div>}
      {!loading && !error && (data?.length ?? 0) === 0 && <div className="empty">No strategies proposed yet.</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {(data ?? []).map((s) => (
          <IdeaCard key={`${s.id}:${s.version}`} row={s} />
        ))}
      </div>
    </div>
  );
}

function IdeaCard({ row }: { row: StrategyRow }) {
  const spec = (row.spec ?? {}) as Record<string, unknown>;
  const universe = (spec.universe ?? {}) as { symbols?: string[] };
  const strategy = (spec.strategy ?? {}) as { id?: string };
  const construction = (spec.construction ?? {}) as { scheme?: string; gross?: number };

  return (
    <div style={{ border: "1px solid var(--border)", padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>
          {(spec.name as string) ?? row.name ?? shortId(row.id)}{" "}
          <span className="badge">v{row.version}</span>
        </div>
        <span className="page-sub">{fmtTime(row.created_at)}</span>
      </div>
      <div className="kv" style={{ marginTop: 6, display: "flex", gap: 16, flexWrap: "wrap" }}>
        <span><span className="k">id</span> {shortId(row.id)}</span>
        {strategy.id && <span><span className="k">primitive</span> {strategy.id}</span>}
        {construction.scheme && <span><span className="k">scheme</span> {construction.scheme}</span>}
        {construction.gross != null && <span><span className="k">gross</span> {construction.gross}</span>}
        {universe.symbols && (
          <span><span className="k">universe</span> {universe.symbols.slice(0, 8).join(", ")}{universe.symbols.length > 8 ? "…" : ""}</span>
        )}
      </div>
    </div>
  );
}
