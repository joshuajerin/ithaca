import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { OrderIntentRow, RunRow } from "../types";
import { fmtTime, shortId, stateClass } from "../lib/format";

export function Orders() {
  const intents = useAsync<OrderIntentRow[]>((s) => api.listOrderIntents(s), []);
  const runs = useAsync<RunRow[]>((s) => api.listRuns(undefined, s), []);
  const runnable = useMemo(
    () => (runs.data ?? []).filter((r) => r.kind === "paper" || r.kind === "backtest"),
    [runs.data],
  );
  const [runId, setRunId] = useState("");
  const [symbol, setSymbol] = useState("AAPL");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("1");
  const [limitPrice, setLimitPrice] = useState("200");
  const [error, setError] = useState<string | null>(null);

  const selectedRunId = runId || runnable[0]?.id || "";

  async function create() {
    setError(null);
    if (!selectedRunId) {
      setError("Create or select a run first.");
      return;
    }
    try {
      await api.createOrderIntent({
        run_id: selectedRunId,
        payload: {
          broker: "paper",
          symbol,
          side,
          quantity: Number(quantity),
          order_type: "limit",
          limit_price: Number(limitPrice),
        },
      });
      intents.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function act(id: string, action: "preview" | "submit") {
    setError(null);
    try {
      if (action === "preview") await api.previewOrderIntent(id);
      else await api.submitOrderIntent(id);
      intents.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">Orders</div>
        <button className="btn" onClick={intents.reload}>Refresh</button>
      </div>

      <section className="ops-card">
        <div className="section-head"><span>Paper order intent</span></div>
        <div className="control-form inline">
          <label>Run
            <select value={selectedRunId} onChange={(e) => setRunId(e.target.value)}>
              {runnable.map((r) => (
                <option key={r.id} value={r.id}>{shortId(r.id)} · {r.kind} · {r.state}</option>
              ))}
            </select>
          </label>
          <label>Symbol<input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} /></label>
          <label>Side
            <select value={side} onChange={(e) => setSide(e.target.value as "buy" | "sell")}>
              <option value="buy">buy</option>
              <option value="sell">sell</option>
            </select>
          </label>
          <label>Qty<input value={quantity} onChange={(e) => setQuantity(e.target.value)} /></label>
          <label>Limit<input value={limitPrice} onChange={(e) => setLimitPrice(e.target.value)} /></label>
          <button className="btn primary" onClick={() => void create()}>Create</button>
        </div>
        {error && <div className="banner">{error}</div>}
      </section>

      {intents.loading && <div className="empty">Loading order intents...</div>}
      {intents.error && <div className="banner">Failed to load order intents: {intents.error}</div>}
      {!intents.loading && !intents.error && (intents.data?.length ?? 0) === 0 && <div className="empty">No order intents.</div>}

      {(intents.data?.length ?? 0) > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>Intent</th>
              <th>State</th>
              <th>Run</th>
              <th>Payload</th>
              <th>Orders</th>
              <th>Fills</th>
              <th>Updated</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {intents.data!.map((row) => (
              <tr key={row.intent_id}>
                <td>{shortId(row.intent_id)}</td>
                <td><span className={`badge ${stateClass(row.state)}`}>{row.state}</span></td>
                <td><Link to={`/runs/${row.run_id}`}>{shortId(row.run_id)}</Link></td>
                <td><code className="mono json-inline">{compact(row.payload)}</code></td>
                <td>{row.orders?.length ?? 0}</td>
                <td>{row.fills?.length ?? 0}</td>
                <td>{fmtTime(row.updated_at)}</td>
                <td>
                  <div className="row-actions">
                    <button className="btn" onClick={() => void act(row.intent_id, "preview")}>Preview</button>
                    <button className="btn primary" onClick={() => void act(row.intent_id, "submit")}>Submit</button>
                  </div>
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
  const text = JSON.stringify(value ?? {});
  return text.length > 150 ? `${text.slice(0, 150)}...` : text;
}
