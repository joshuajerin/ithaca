import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface SeriesPoint {
  date: string;
  book: number;
  drawdown: number;
}

interface PerformanceStats {
  totalReturn?: number;
  cagr?: number;
  vol?: number;
  sharpe?: number;
  sortino?: number;
  maxDD?: number;
  hitRate?: number;
}

export interface PerformancePnlData {
  portfolioName: string;
  rangeLabel: string;
  windowPoints: number;
  series: SeriesPoint[];
  stats: PerformanceStats;
  stale: boolean;
}

function signed(value: number, digits = 2): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function tone(value: number): string {
  return value > 0 ? "var(--pos)" : value < 0 ? "var(--neg)" : "var(--muted)";
}

function Stat({ label, value, percent = false }: { label: string; value: number; percent?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 8.5, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted)" }}>{label}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: tone(value) }}>
        {percent ? signed(value) : value.toFixed(2)}
      </span>
    </div>
  );
}

export function PerformancePnlPanel({ data }: { data: PerformancePnlData }) {
  const metrics = [
    ["Return", data.stats.totalReturn, true],
    ["CAGR", data.stats.cagr, true],
    ["Volatility", data.stats.vol, true],
    ["Sharpe", data.stats.sharpe, false],
    ["Sortino", data.stats.sortino, false],
    ["Max drawdown", data.stats.maxDD, true],
    ["Hit rate", data.stats.hitRate, true],
  ] as const;

  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>
          {data.portfolioName} · realized backtest evidence
        </div>
        <div style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>
          {data.stale ? "Stale evidence · " : ""}{data.rangeLabel} · {data.windowPoints} points
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 180 }}>
        <ResponsiveContainer width="100%" height="68%">
          <ComposedChart data={data.series} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="var(--border-soft)" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} minTickGap={40} />
            <YAxis tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} tickFormatter={(value) => `${value}%`} />
            <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
            <ReferenceLine y={0} stroke="var(--border)" />
            <Line type="monotone" dataKey="book" stroke="var(--fg)" strokeWidth={1.6} dot={false} name="Return" />
          </ComposedChart>
        </ResponsiveContainer>
        <ResponsiveContainer width="100%" height="32%">
          <ComposedChart data={data.series} margin={{ top: 0, right: 4, left: -22, bottom: 0 }}>
            <XAxis dataKey="date" hide />
            <YAxis tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} tickFormatter={(value) => `${value}%`} />
            <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
            <Area type="monotone" dataKey="drawdown" stroke="var(--neg)" fill="var(--neg)" fillOpacity={0.12} name="Drawdown" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: "8px 16px", borderTop: "1px solid var(--border-soft)", paddingTop: 10 }}>
        {metrics.map(([label, value, percent]) =>
          typeof value === "number" ? <Stat key={label} label={label} value={value} percent={percent} /> : null,
        )}
      </div>
    </div>
  );
}
