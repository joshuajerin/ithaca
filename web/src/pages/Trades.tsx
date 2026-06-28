import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { RunRow } from "../types";
import { fmtTime, shortId } from "../lib/format";

interface TradeRow {
  runId: string;
  ts: string;
  symbol: string;
  side: string;
  qty: number | string;
  price: number | string;
}

// Trades are fills harvested from paper-run result artifacts. The fill TraceEvents also
// stream live into a run page; this view is the cross-run ledger from persisted results.
export function Trades() {
  const { data, loading, error } = useAsync<RunRow[]>((s) => api.listRuns("paper", s), []);
  const navigate = useNavigate();

  const trades: TradeRow[] = [];
  for (const r of data ?? []) {
    const result = (r.result ?? {}) as Record<string, unknown>;
    const fills = (result.fills ?? (result.data as Record<string, unknown> | undefined)?.fills) as
      | Record<string, unknown>[]
      | undefined;
    if (Array.isArray(fills)) {
      for (const f of fills) {
        trades.push({
          runId: r.id,
          ts: String(f.ts ?? f.time ?? r.updated_at ?? ""),
          symbol: String(f.symbol ?? f.sym ?? "—"),
          side: String(f.side ?? f.action ?? "—"),
          qty: (f.qty ?? f.quantity ?? "—") as number | string,
          price: (f.price ?? "—") as number | string,
        });
      }
    }
  }
  trades.sort((a, b) => (a.ts < b.ts ? 1 : -1));

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="page-title">Trades</div>
        </div>
      </div>

      {error && <div className="banner">Failed to load: {error}</div>}
      {loading && <div className="empty">Loading trades…</div>}
      {!loading && !error && trades.length === 0 && (
        <div className="empty">No trades.</div>
      )}

      {trades.length > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Side</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Run</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} onClick={() => navigate(`/runs/${t.runId}`)}>
                <td>{fmtTime(t.ts)}</td>
                <td>{t.symbol}</td>
                <td style={{ color: /buy|long/i.test(t.side) ? "var(--pos)" : "var(--neg)" }}>{t.side}</td>
                <td>{String(t.qty)}</td>
                <td>{typeof t.price === "number" ? t.price.toFixed(2) : t.price}</td>
                <td>{shortId(t.runId)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
