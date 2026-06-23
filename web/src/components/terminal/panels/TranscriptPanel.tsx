// @ts-nocheck
import React, { useState, useMemo } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine } from "recharts";
import { Quote } from "lucide-react";

interface TranscriptSegment {
  index: number;
  speaker: string;
  role: string;
  text: string;
  sentiment: number;
  sentimentLabel: string;
  isKeyQuote: boolean;
}

interface TranscriptKeyQuote {
  speaker: string;
  role: string;
  text: string;
  topic: string;
}

interface TranscriptSentPoint {
  index: number;
  score: number;
  label: string;
}

interface TranscriptData {
  symbol: string;
  name: string;
  callDate: string;
  quarter: string;
  overallSentiment: number;
  segments: TranscriptSegment[];
  keyQuotes: TranscriptKeyQuote[];
  sentimentTimeline: TranscriptSentPoint[];
}

const ROLE_COLORS: Record<string, string> = {
  CEO: "text-white",
  CFO: "text-blue-300",
  Analyst: "text-yellow-400",
  Operator: "text-muted-foreground",
};

const SENT_COLORS: Record<string, string> = {
  positive: "border-l-emerald-400",
  neutral: "border-l-gray-600",
  negative: "border-l-red-400",
};

export function TranscriptPanel({ data }: { data: TranscriptData }) {
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState<"transcript" | "quotes" | "sentiment">("transcript");

  const filteredSegments = useMemo(() => {
    if (!search.trim()) return data.segments;
    const q = search.toLowerCase();
    return data.segments.filter(
      s => s.text.toLowerCase().includes(q) || s.speaker.toLowerCase().includes(q)
    );
  }, [data.segments, search]);

  const overallLabel = data.overallSentiment > 0.65 ? "POSITIVE" : data.overallSentiment < 0.4 ? "NEGATIVE" : "NEUTRAL";
  const overallColor = data.overallSentiment > 0.65 ? "text-emerald-400" : data.overallSentiment < 0.4 ? "text-red-400" : "text-gray-300";

  function highlight(text: string, query: string): React.ReactNode {
    if (!query.trim()) return text;
    const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
    return parts.map((p, i) =>
      p.toLowerCase() === query.toLowerCase() ? <mark key={i} className="bg-yellow-400/30 text-white">{p}</mark> : p
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div>
          <span className="text-xs font-bold uppercase">{data.symbol}</span>
          <span className="text-[10px] text-muted-foreground ml-2">{data.name} · {data.quarter} · {data.callDate}</span>
        </div>
        <div className={`text-[10px] font-bold uppercase tracking-widest ${overallColor}`}>
          {overallLabel} {(data.overallSentiment * 100).toFixed(0)}%
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-2 shrink-0">
        {(["transcript", "quotes", "sentiment"] as const).map(t => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`text-[10px] uppercase tracking-widest px-2 py-0.5 border transition-colors ${
              activeTab === t ? "border-white text-white bg-white/10" : "border-border text-muted-foreground hover:border-gray-500"
            }`}
          >
            {t === "quotes" ? "Key Quotes" : t}
          </button>
        ))}
      </div>

      {activeTab === "sentiment" && (
        <div className="flex-1 min-h-0">
          <div className="text-[9px] text-muted-foreground uppercase tracking-wider mb-2">Sentiment by Segment</div>
          <ResponsiveContainer width="100%" height="85%">
            <LineChart data={data.sentimentTimeline} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
              <XAxis dataKey="index" tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} label={{ value: "Segment", position: "insideBottom", fontSize: 8, fill: "#555" }} />
              <YAxis domain={[0, 1]} tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
              <ReferenceLine y={0.5} stroke="#444" strokeDasharray="3 3" />
              <Tooltip
                contentStyle={{ backgroundColor: "#000", borderColor: "#333", fontSize: 10 }}
                formatter={(v: number, _: string, props: any) => [
                  `${(v * 100).toFixed(0)}% (${props.payload?.label || ""})`,
                  "Sentiment"
                ]}
              />
              <Line
                type="monotone"
                dataKey="score"
                stroke="#fff"
                strokeWidth={1.5}
                dot={(props: any) => {
                  const { cx, cy, payload } = props;
                  const color = payload.label === "positive" ? "#34d399" : payload.label === "negative" ? "#f87171" : "#888";
                  return <circle key={props.key} cx={cx} cy={cy} r={3} fill={color} stroke="none" />;
                }}
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="flex gap-3 mt-1 justify-center">
            {[["positive", "#34d399"], ["neutral", "#888"], ["negative", "#f87171"]].map(([label, color]) => (
              <span key={label} className="flex items-center gap-1 text-[9px]" style={{ color }}>
                <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: color }} />{label}
              </span>
            ))}
          </div>
        </div>
      )}

      {activeTab === "quotes" && (
        <ScrollArea className="flex-1 min-h-0">
          <div className="flex flex-col gap-3">
            {data.keyQuotes.length === 0 && (
              <div className="text-xs text-muted-foreground">No key quotes extracted.</div>
            )}
            {data.keyQuotes.map((q, i) => (
              <div key={i} className="border border-border/60 p-3 bg-white/3 hover:bg-white/5 transition-colors">
                <div className="flex items-center gap-2 mb-2">
                  <Quote className="w-3 h-3 text-muted-foreground shrink-0" />
                  <span className={`text-[10px] font-bold uppercase ${ROLE_COLORS[q.role] || "text-white"}`}>{q.speaker}</span>
                  <span className="text-[9px] text-muted-foreground">{q.role}</span>
                  <span className="ml-auto text-[9px] border border-white/20 text-white/60 px-1.5 py-0.5 uppercase tracking-wider">{q.topic}</span>
                </div>
                <p className="text-xs text-gray-300 leading-relaxed font-serif">"{q.text}"</p>
              </div>
            ))}
          </div>
        </ScrollArea>
      )}

      {activeTab === "transcript" && (
        <>
          <div className="mb-2 shrink-0">
            <input
              type="text"
              placeholder="Search transcript..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-black border border-border px-2 py-1 text-xs text-white focus:outline-none focus:border-white transition-colors placeholder:text-muted-foreground"
            />
          </div>
          <ScrollArea className="flex-1 min-h-0">
            <div className="flex flex-col gap-2 pr-1">
              {filteredSegments.length === 0 && (
                <div className="text-xs text-muted-foreground">No results for "{search}".</div>
              )}
              {filteredSegments.map((seg, i) => (
                <div
                  key={seg.index}
                  className={`border-l-2 pl-3 py-1 ${SENT_COLORS[seg.sentimentLabel] || "border-l-gray-600"} ${seg.isKeyQuote ? "bg-white/3" : ""}`}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className={`text-[10px] font-bold uppercase ${ROLE_COLORS[seg.role] || "text-white"}`}>{seg.speaker}</span>
                    <span className="text-[9px] text-muted-foreground">{seg.role}</span>
                    {seg.isKeyQuote && (
                      <span className="ml-auto text-[9px] text-yellow-400/80 uppercase tracking-wider">★ Key Quote</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 leading-relaxed">
                    {highlight(seg.text, search)}
                  </p>
                </div>
              ))}
            </div>
          </ScrollArea>
        </>
      )}
    </div>
  );
}
