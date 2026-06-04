import React from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

function Bps({ value, label }: { value: number; label: string }) {
  return (
    <div className="border-t border-border pt-2">
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-0.5">{label}</div>
      <div className="text-sm font-bold font-mono">{value.toFixed(2)} bps</div>
    </div>
  );
}

function PriceRow({ label, price, isHighlight }: { label: string; price: number; isHighlight?: boolean }) {
  return (
    <div className={`flex justify-between items-baseline py-1 border-b border-border/40 ${isHighlight ? "text-white" : "text-muted-foreground"}`}>
      <span className="text-[10px] uppercase tracking-wider">{label}</span>
      <span className={`font-mono text-sm ${isHighlight ? "font-bold" : ""}`}>${price.toFixed(2)}</span>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-black border border-border text-xs p-2 space-y-1">
      <div className="font-bold text-[10px] uppercase tracking-wider">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex justify-between gap-3">
          <span className="text-muted-foreground">{p.name}</span>
          <span className="font-mono">
            {p.dataKey === "participationRate"
              ? `${(p.value * 100).toFixed(1)}%`
              : `$${Number(p.value).toFixed(2)}`}
          </span>
        </div>
      ))}
    </div>
  );
};

export function TCAPanelReport({ data }: { data: any }) {
  const better = data.avgExecPrice <= data.vwap;

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest">
            {data.symbol} · TCA Report
          </div>
          <div className="text-sm font-bold uppercase text-muted-foreground">
            {better ? "Outperformed VWAP" : "Underperformed VWAP"}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest">Impl. Shortfall</div>
          <div className="text-lg font-bold font-mono">{data.implementationShortfall.toFixed(2)} bps</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-6 shrink-0">
        <div>
          <PriceRow label="Arrival" price={data.arrivalPrice} />
          <PriceRow label="Avg Exec" price={data.avgExecPrice} isHighlight />
        </div>
        <div>
          <PriceRow label="VWAP" price={data.vwap} isHighlight />
          <PriceRow label="TWAP" price={data.twap} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 shrink-0">
        <Bps value={data.implementationShortfall} label="IS" />
        <Bps value={data.vwapSlippage} label="VWAP Slip" />
        <Bps value={data.twapSlippage} label="TWAP Slip" />
      </div>

      <div className="flex-1 min-h-0">
        <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">
          Intraday Execution vs Benchmarks
        </div>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data.buckets} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              interval={2}
            />
            <YAxis
              yAxisId="price"
              domain={["auto", "auto"]}
              tick={{ fontSize: 9, fill: "#555" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${v.toFixed(0)}`}
            />
            <YAxis
              yAxisId="rate"
              orientation="right"
              domain={[0, "auto"]}
              tick={{ fontSize: 9, fill: "#444" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Bar
              yAxisId="rate"
              dataKey="participationRate"
              name="Part. Rate"
              fill="#ffffff"
              opacity={0.12}
              barSize={8}
            />
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="execPrice"
              name="Exec"
              stroke="#ffffff"
              strokeWidth={1.5}
              dot={false}
            />
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="vwap"
              name="VWAP"
              stroke="#666666"
              strokeWidth={1}
              strokeDasharray="4 2"
              dot={false}
            />
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="twap"
              name="TWAP"
              stroke="#444444"
              strokeWidth={1}
              strokeDasharray="2 2"
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
