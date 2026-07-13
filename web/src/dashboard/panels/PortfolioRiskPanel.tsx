export interface PortfolioRiskData {
  metrics: Record<string, number>;
  holdings: Array<{ symbol: string; weight: number }>;
  capital: number | null;
  gross: number | null;
  cash: number | null;
  asOf: string | null;
  stale: boolean;
}

const METRIC_LABELS: Record<string, string> = {
  var95: "1-day 95% VaR",
  trackingError: "Tracking error",
  tracking_error: "Tracking error",
  beta: "Beta",
  vol: "Volatility",
  volatility: "Volatility",
  maxDD: "Max drawdown",
  max_drawdown: "Max drawdown",
  sharpe: "Sharpe",
};

function formatMetric(key: string, value: number): string {
  const percent = /var|error|vol|maxdd|drawdown/i.test(key);
  return `${value.toFixed(2)}${percent ? "%" : ""}`;
}

export function PortfolioRiskPanel({ data }: { data: PortfolioRiskData }) {
  const metrics = Object.entries(data.metrics).filter(([key]) => key in METRIC_LABELS);
  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 16 }}>
      {metrics.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 10 }}>
          {metrics.map(([key, value]) => (
            <div key={key} style={{ border: "1px solid var(--border-soft)", padding: 10, borderRadius: "var(--radius-sm)" }}>
              <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 5 }}>{METRIC_LABELS[key]}</div>
              <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "var(--font-mono)" }}>{formatMetric(key, value)}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 10 }}>
        {data.capital != null && <div><small>Capital</small><strong>${data.capital.toLocaleString()}</strong></div>}
        {data.gross != null && <div><small>Gross exposure</small><strong>{(data.gross * 100).toFixed(1)}%</strong></div>}
        {data.cash != null && <div><small>Cash</small><strong>${data.cash.toLocaleString()}</strong></div>}
      </div>

      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 8 }}>Recorded holdings</div>
        {data.holdings.length === 0 ? (
          <div className="empty">No paper positions recorded.</div>
        ) : (
          <div style={{ display: "grid", gap: 7 }}>
            {data.holdings.map(({ symbol, weight }) => (
              <div key={symbol} style={{ display: "grid", gridTemplateColumns: "70px 1fr 56px", alignItems: "center", gap: 8 }}>
                <strong style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{symbol}</strong>
                <div style={{ height: 6, background: "var(--border-soft)", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ width: `${Math.min(100, Math.abs(weight) * 100)}%`, height: "100%", background: weight >= 0 ? "var(--pos)" : "var(--neg)" }} />
                </div>
                <span style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 10 }}>{(weight * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>
      {(data.asOf || data.stale) && (
        <small style={{ color: data.stale ? "var(--neg)" : "var(--muted)" }}>
          {data.stale ? "Stale evidence" : "Recorded evidence"}{data.asOf ? ` · as of ${data.asOf}` : ""}
        </small>
      )}
    </div>
  );
}
