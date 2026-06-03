import React from "react";
import type { PriceChartData } from "@workspace/api-client-react/src/generated/api.schemas";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine } from "recharts";

interface PriceChartPanelProps {
  data: PriceChartData;
}

export function PriceChartPanel({ data }: PriceChartPanelProps) {
  const isPositive = data.change >= 0;
  
  // Create a minimal tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-black border border-white p-2 shadow-xl">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-sm font-bold mt-1">
            {payload[0].value.toFixed(2)}
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex justify-between items-end mb-4 shrink-0">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold">{data.symbol}</span>
            <span className="text-xs text-muted-foreground uppercase">{data.name}</span>
          </div>
          <div className="text-[10px] text-muted-foreground mt-1 uppercase tracking-widest">
            {data.range} Range
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold tracking-tight">
            {data.currency} {data.last.toFixed(2)}
          </div>
          <div className={`text-sm font-bold flex items-center justify-end gap-1 ${isPositive ? 'text-white' : 'text-muted-foreground'}`}>
            {isPositive ? '+' : ''}{data.change.toFixed(2)} ({isPositive ? '+' : ''}{data.changePct.toFixed(2)}%)
          </div>
        </div>
      </div>

      <div className="flex-1 w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.points} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 2" stroke="#333" vertical={false} />
            <XAxis 
              dataKey="t" 
              tick={{ fontSize: 10, fill: '#666' }} 
              tickLine={false} 
              axisLine={false}
              minTickGap={30}
            />
            <YAxis 
              domain={['auto', 'auto']} 
              tick={{ fontSize: 10, fill: '#666' }} 
              tickLine={false} 
              axisLine={false}
              tickFormatter={(val) => val.toFixed(1)}
            />
            <Tooltip content={<CustomTooltip />} />
            {data.points.length > 0 && (
              <ReferenceLine y={data.points[0].c} stroke="#444" strokeDasharray="3 3" />
            )}
            <Line 
              type="monotone" 
              dataKey="c" 
              stroke="#fff" 
              strokeWidth={1.5} 
              dot={false}
              activeDot={{ r: 4, fill: '#000', stroke: '#fff', strokeWidth: 2 }} 
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
