import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { Sparkles, AlertCircle, ListChecks } from "lucide-react";

interface Assumption {
  label: string;
  detail: string;
  impactPct?: number;
}

interface PathPoint {
  step: number;
  baselineP50: number;
  scenarioP50: number;
  baselineP5?: number;
  baselineP95?: number;
  scenarioP5?: number;
  scenarioP95?: number;
}

interface Leg {
  expectedReturnPct: number;
  endValue: number;
  p5Pct?: number;
  p95Pct?: number;
  deltaPct?: number;
  probLossPct?: number;
}

interface Projection {
  horizon: number;
  method: string;
  startValue: number;
  path: PathPoint[];
  baseline: Leg;
  scenario: Leg;
}

interface ScenarioData {
  prompt: string;
  scope: string;
  symbols: string[];
  horizonDays: number;
  basis: "grounded" | "estimated";
  driftPct: number;
  assumptions: Assumption[];
  reasoning: string;
  caveats: string[];
  projection?: Projection | null;
}

function pct(n?: number): string {
  if (n === null || n === undefined) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

export function ScenarioPanel({ data }: { data: ScenarioData }) {
  const proj = data.projection;

  const ScenarioTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      const row = proj?.path[label] ?? proj?.path.find((p) => p.step === label);
      if (!row) return null;
      return (
        <div className="bg-black border border-white/20 p-2 text-xs space-y-0.5">
          <p className="text-muted-foreground">Day {row.step}</p>
          <p className="text-white font-mono">scenario: {row.scenarioP50.toFixed(1)}</p>
          <p className="text-muted-foreground font-mono">baseline: {row.baselineP50.toFixed(1)}</p>
        </div>
      );
    }
    return null;
  };

  const scenUp = proj ? proj.scenario.expectedReturnPct >= proj.baseline.expectedReturnPct : true;

  return (
    <ScrollArea className="h-full pr-1">
      <div className="flex flex-col gap-5 pb-2">

        {/* ── Header: the what-if ── */}
        <section className="border-b border-border pb-3">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
            <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">What-If</span>
            <span className={`ml-auto px-1.5 py-0.5 border editorial-label text-[7.5px] uppercase tracking-widest ${
              data.basis === "grounded" ? "border-white/40 text-white" : "border-border text-muted-foreground"
            }`}>
              {data.basis === "grounded" ? "grounded sim" : "estimated"}
            </span>
          </div>
          <p className="font-serif text-[15px] text-white leading-snug">{data.prompt}</p>
          <div className="flex items-center gap-2 mt-2 editorial-label text-[7.5px] text-muted-foreground tracking-widest uppercase">
            <span>{data.scope}</span>
            <span>·</span>
            <span>{data.horizonDays}d horizon</span>
            {data.symbols && data.symbols.length > 0 && (
              <>
                <span>·</span>
                <span className="truncate">{data.symbols.slice(0, 5).join(" / ")}</span>
              </>
            )}
          </div>
        </section>

        {/* ── Outcome: baseline vs scenario ── */}
        {proj && (
          <section className="grid grid-cols-2 gap-3 border-b border-border pb-4">
            <div className="border border-border p-3">
              <div className="editorial-label text-[7.5px] text-muted-foreground tracking-widest uppercase mb-1">Baseline</div>
              <div className="font-serif text-xl text-gray-300 nums-tabular">{pct(proj.baseline.expectedReturnPct)}</div>
              <div className="editorial-label text-[7.5px] text-muted-foreground mt-1 nums-tabular">
                p5 {pct(proj.baseline.p5Pct)} · p95 {pct(proj.baseline.p95Pct)}
              </div>
            </div>
            <div className={`border p-3 ${scenUp ? "border-white/50 bg-white/[0.04]" : "border-muted-foreground/40 bg-muted/10"}`}>
              <div className="editorial-label text-[7.5px] text-muted-foreground tracking-widest uppercase mb-1">
                Scenario {proj.scenario.deltaPct !== undefined && (
                  <span className="text-white">({pct(proj.scenario.deltaPct)} vs base)</span>
                )}
              </div>
              <div className="font-serif text-xl text-white nums-tabular">{pct(proj.scenario.expectedReturnPct)}</div>
              <div className="editorial-label text-[7.5px] text-muted-foreground mt-1 nums-tabular">
                p5 {pct(proj.scenario.p5Pct)} · p95 {pct(proj.scenario.p95Pct)}
              </div>
            </div>
          </section>
        )}

        {/* ── Projected paths ── */}
        {proj && proj.path && proj.path.length > 0 && (
          <section>
            <div className="editorial-label text-[8px] text-muted-foreground tracking-widest uppercase mb-2">
              Projected Path · {proj.method.toUpperCase()} · rebased to {proj.startValue}
            </div>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={proj.path} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                  <XAxis
                    dataKey="step"
                    tick={{ fontSize: 9, fill: "#555" }}
                    tickLine={false}
                    axisLine={false}
                    minTickGap={40}
                    tickFormatter={(v) => `${v}d`}
                  />
                  <YAxis tick={{ fontSize: 9, fill: "#555" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
                  <Tooltip content={<ScenarioTooltip />} />
                  <ReferenceLine y={proj.startValue} stroke="#666" strokeDasharray="4 2" />
                  <Line type="monotone" dataKey="baselineP50" stroke="#888888" strokeWidth={1.25} strokeDasharray="4 2" dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="scenarioP50" stroke="#ffffff" strokeWidth={1.75} dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="flex items-center gap-4 mt-1 editorial-label text-[7.5px] text-muted-foreground tracking-widest uppercase">
              <span className="flex items-center gap-1.5"><span className="inline-block w-4 h-px bg-white" /> Scenario</span>
              <span className="flex items-center gap-1.5"><span className="inline-block w-4 border-t border-dashed border-[#888]" /> Baseline</span>
            </div>
          </section>
        )}

        {/* ── Assumptions / inputs ── */}
        {data.assumptions && data.assumptions.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-3">
              <ListChecks className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
              <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Assumptions</span>
              <span className="editorial-label text-[8px] text-white ml-auto nums-tabular">net {pct(data.driftPct)} / yr</span>
            </div>
            <div className="flex flex-col border-t border-border">
              {data.assumptions.map((a, i) => (
                <div key={i} className="flex gap-3 py-2.5 border-b border-border last:border-b-0">
                  <span className="editorial-label text-[8px] text-muted-foreground mt-0.5 nums-tabular shrink-0 w-4">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start gap-2 mb-1">
                      <span className="font-serif text-sm text-white leading-tight flex-1">{a.label}</span>
                      {a.impactPct !== undefined && (
                        <span className="editorial-label text-[8px] text-muted-foreground nums-tabular shrink-0">{pct(a.impactPct)}</span>
                      )}
                    </div>
                    <p className="editorial-label text-[8.5px] text-muted-foreground leading-relaxed">{a.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Reasoning ── */}
        {data.reasoning && (
          <section>
            <div className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase mb-2">Reasoning</div>
            <p className="font-serif text-[13px] text-gray-200 leading-relaxed">{data.reasoning}</p>
          </section>
        )}

        {/* ── Caveats ── */}
        {data.caveats && data.caveats.length > 0 && (
          <section className="border border-border bg-white/[0.02] p-3">
            <div className="flex items-center gap-2 mb-2">
              <AlertCircle className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
              <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Caveats</span>
            </div>
            <ul className="flex flex-col gap-1.5">
              {data.caveats.map((c, i) => (
                <li key={i} className="editorial-label text-[8.5px] text-muted-foreground leading-relaxed flex gap-2">
                  <span className="text-gray-600">—</span>
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

      </div>
    </ScrollArea>
  );
}
