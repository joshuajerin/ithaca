// @ts-nocheck
import React from "react";
import type { SentimentData } from "@workspace/api-client-react";
import { AreaChart, Area, XAxis, Tooltip, CartesianGrid } from "recharts";

function useChartSize() {
  const ref = React.useRef<HTMLDivElement | null>(null);
  const [size, setSize] = React.useState({ width: 0, height: 0 });

  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    let frame = 0;
    const check = () => {
      const rect = el.getBoundingClientRect();
      setSize({
        width: Math.max(0, Math.floor(rect.width)),
        height: Math.max(0, Math.floor(rect.height)),
      });
    };

    frame = requestAnimationFrame(check);
    const observer = new ResizeObserver(check);
    observer.observe(el);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  return [ref, size] as const;
}

export function SentimentPanel({ data }: { data: SentimentData }) {
  const isPositive = data.overall > 0;
  const [chartRef, chartSize] = useChartSize();
  
  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-end mb-5 shrink-0">
        <div>
          <div className="font-serif text-3xl leading-none capitalize">
            {data.label.replace('_', ' ').toLowerCase()}
          </div>
        </div>
        <div className={`font-serif text-4xl leading-none nums-oldstyle ${isPositive ? 'text-white' : 'text-muted-foreground'}`}>
          {data.overall > 0 ? '+' : ''}{data.overall.toFixed(2)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3 mb-5 shrink-0">
        {data.sources.map(source => (
          <div key={source.channel} className="border-t border-border pt-2">
            <div className="flex justify-between items-baseline mb-1.5">
              <span className="editorial-label text-[8.5px] text-muted-foreground">{source.channel}</span>
              <span className={`font-serif text-sm nums-oldstyle ${source.score > 0 ? 'text-white' : 'text-gray-500'}`}>
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

      <div ref={chartRef} className="flex-1 w-full min-h-[100px]">
        {chartSize.width > 0 && chartSize.height > 0 ? (
          <AreaChart
            width={chartSize.width}
            height={chartSize.height}
            data={data.trend}
            margin={{ top: 5, right: 0, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#fff" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#fff" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="1 3" stroke="#222" vertical={false} />
            <XAxis dataKey="t" tick={{ fontSize: 9, fill: '#777', fontFamily: 'var(--font-sans)' }} tickLine={false} axisLine={false} minTickGap={20} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#000', borderColor: '#fff', borderRadius: 0, color: '#fff', fontFamily: 'var(--font-sans)' }}
              itemStyle={{ color: '#fff' }}
              labelStyle={{ color: '#888', fontFamily: 'var(--font-sans)', textTransform: 'uppercase', fontSize: 9 }}
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
        ) : null}
      </div>
    </div>
  );
}
