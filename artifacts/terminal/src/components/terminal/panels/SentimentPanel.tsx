import React from "react";
import type { SentimentData } from "@workspace/api-client-react";
import { ResponsiveContainer, AreaChart, Area, XAxis, Tooltip, CartesianGrid } from "recharts";

export function SentimentPanel({ data }: { data: SentimentData }) {
  const isPositive = data.overall > 0;
  
  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-end mb-4 shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">
            {data.scope} SENTIMENT
          </div>
          <div className="text-2xl font-bold uppercase tracking-widest">
            {data.label.replace('_', ' ')}
          </div>
        </div>
        <div className={`text-3xl font-mono tracking-tighter ${isPositive ? 'text-white' : 'text-muted-foreground'}`}>
          {data.overall > 0 ? '+' : ''}{data.overall.toFixed(2)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4 shrink-0">
        {data.sources.map(source => (
          <div key={source.channel} className="border-t border-border pt-2">
            <div className="flex justify-between items-center mb-1">
              <span className="text-[10px] uppercase text-muted-foreground">{source.channel}</span>
              <span className={`text-xs font-bold ${source.score > 0 ? 'text-white' : 'text-gray-500'}`}>
                {source.score > 0 ? '+' : ''}{source.score.toFixed(1)}
              </span>
            </div>
            <div className="w-full h-1 bg-[#111] overflow-hidden">
              <div 
                className={`h-full ${source.score > 0 ? 'bg-white' : 'bg-gray-600'}`}
                style={{ 
                  width: `${Math.min(100, Math.abs(source.score) * 100)}%`,
                  marginLeft: source.score < 0 ? `${100 - Math.min(100, Math.abs(source.score) * 100)}%` : '0' 
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="flex-1 w-full min-h-[100px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data.trend} margin={{ top: 5, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#fff" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#fff" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 2" stroke="#222" vertical={false} />
            <XAxis dataKey="t" tick={{ fontSize: 9, fill: '#666' }} tickLine={false} axisLine={false} minTickGap={20} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#000', borderColor: '#333', borderRadius: 0, color: '#fff' }}
              itemStyle={{ color: '#fff' }}
              formatter={(value: number) => [value.toFixed(2), 'Score']}
            />
            <Area 
              type="monotone" 
              dataKey="score" 
              stroke="#fff" 
              fillOpacity={1} 
              fill="url(#colorScore)" 
              strokeWidth={1.5}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
