// @ts-nocheck
import React, { useCallback, useEffect, useRef, useState } from "react";
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
import { Sparkles, AlertCircle, ListChecks, SlidersHorizontal, Loader2, RotateCcw } from "lucide-react";
import { recomputeScenario } from "@workspace/api-client-react";

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
  p5Value?: number;
  p95Value?: number;
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
  investment?: number | null;
}

function pct(n?: number): string {
  if (n === null || n === undefined) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function usd(v?: number | null, compact = false): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  return v.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    notation: compact && abs >= 10000 ? "compact" : "standard",
    maximumFractionDigits: abs >= 1000 || compact ? 0 : 2,
  });
}

const RECOMPUTE_TIMEOUT_MS = 12000;
const DEBOUNCE_MS = 450;

export function ScenarioPanel({ data }: { data: ScenarioData }) {
  // Local, editable copies of the projection inputs. They reset whenever a fresh
  // scenario arrives from the agent, but otherwise let the user nudge the
  // assumptions and instantly re-run the projection without retyping a prompt.
  const [proj, setProj] = useState<Projection | null | undefined>(data.projection);
  const [horizon, setHorizon] = useState<number>(data.horizonDays);
  const [drift, setDrift] = useState<number>(data.driftPct);
  const [impacts, setImpacts] = useState<number[]>(
    () => (data.assumptions || []).map((a) => a.impactPct ?? 0),
  );
  const [dirty, setDirty] = useState(false);
  const [recomputing, setRecomputing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  // Dollar amount invested. When set, baseline/scenario outcomes are shown in
  // dollars. `amountInput` is the editable text field; committed on Enter/blur.
  const [amount, setAmount] = useState<number | null>(data.investment ?? null);
  const [amountInput, setAmountInput] = useState<string>(
    data.investment ? String(Math.round(data.investment)) : "",
  );

  const canTune = Boolean(data.projection) && (data.symbols?.length ?? 0) > 0;
  const hasMoney = (amount ?? 0) > 0;

  // A stable signature of the *parsed* scenario. We only reset local edits when
  // a genuinely new scenario arrives (the agent re-parsed a prompt) — not on
  // every incidental parent re-render, which would otherwise wipe the user's
  // in-progress tweaks and the recomputed projection.
  const sig = `${data.prompt}|${data.scope}|${(data.symbols || []).join(",")}|${data.horizonDays}|${data.driftPct}`;

  useEffect(() => {
    setProj(data.projection);
    setHorizon(data.horizonDays);
    setDrift(data.driftPct);
    setImpacts((data.assumptions || []).map((a) => a.impactPct ?? 0));
    setAmount(data.investment ?? null);
    setAmountInput(data.investment ? String(Math.round(data.investment)) : "");
    setDirty(false);
    setNotice(null);
    setRecomputing(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig]);

  // Keep mutable inputs in a ref so `runRecompute` stays referentially stable.
  // Otherwise its identity would change whenever the parent passes a new `data`
  // object, retriggering (and continually rescheduling) the debounce effect —
  // which can starve the timer so the recompute never actually fires.
  const liveRef = useRef({ symbols: data.symbols, canTune, amount });
  liveRef.current = { symbols: data.symbols, canTune, amount };

  const runRecompute = useCallback(async (nextHorizon: number, nextDrift: number) => {
    const { symbols, canTune: tunable, amount: amt } = liveRef.current;
    if (!tunable) return;
    setRecomputing(true);
    setNotice(null);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), RECOMPUTE_TIMEOUT_MS);
    try {
      const res = await recomputeScenario(
        {
          symbols,
          horizonDays: nextHorizon,
          driftPct: nextDrift,
          ...((amt ?? 0) > 0 ? { amount: amt as number } : {}),
        },
        { signal: controller.signal },
      );
      if (res?.projection) {
        setProj(res.projection as unknown as Projection);
        setNotice(null);
      } else {
        setNotice("Recompute returned no projection — showing the previous result.");
      }
    } catch (err) {
      // Timed out or failed: keep the prior projection, surface a quiet notice.
      setNotice("Couldn't re-run the projection just now — showing the previous result.");
    } finally {
      clearTimeout(timer);
      setRecomputing(false);
    }
  }, []);

  // Debounced re-run whenever the user changes horizon, net drift, or the
  // invested dollar amount. Depend on primitives only (not `data`/`runRecompute`)
  // so unrelated re-renders don't reset the timer.
  useEffect(() => {
    if (!dirty || !canTune) return;
    const t = setTimeout(() => void runRecompute(horizon, drift), DEBOUNCE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [horizon, drift, amount, dirty]);

  const commitAmount = () => {
    const parsed = Number(amountInput.replace(/[^0-9.]/g, ""));
    if (Number.isFinite(parsed) && parsed > 0) {
      if (parsed !== amount) {
        setDirty(true);
        setAmount(parsed);
      }
    } else {
      // Empty / invalid clears the dollar denomination back to the index base.
      if (amount !== null) {
        setDirty(true);
        setAmount(null);
      }
      setAmountInput("");
    }
  };

  const onHorizon = (v: number) => {
    setDirty(true);
    setHorizon(v);
  };
  const onDrift = (v: number) => {
    setDirty(true);
    setDrift(Number(v.toFixed(1)));
  };
  const onImpact = (idx: number, v: number) => {
    setDirty(true);
    setImpacts((prev) => {
      const next = prev.slice();
      next[idx] = v;
      // Per-assumption impacts sum into the net drift that drives the projection.
      const sum = next.reduce((acc, x) => acc + (Number.isFinite(x) ? x : 0), 0);
      setDrift(Number(sum.toFixed(1)));
      return next;
    });
  };

  const reset = () => {
    setProj(data.projection);
    setHorizon(data.horizonDays);
    setDrift(data.driftPct);
    setImpacts((data.assumptions || []).map((a) => a.impactPct ?? 0));
    setDirty(false);
    setNotice(null);
  };

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
            <span>{horizon}d horizon</span>
            {data.symbols && data.symbols.length > 0 && (
              <>
                <span>·</span>
                <span className="truncate">{data.symbols.slice(0, 5).join(" / ")}</span>
              </>
            )}
          </div>
        </section>

        {/* ── Invested amount: denominate outcomes in dollars ── */}
        {canTune && (
          <section className="border-b border-border pb-3 flex items-center gap-2">
            <span className="editorial-label text-[8px] text-muted-foreground tracking-widest uppercase">Invest</span>
            <div className="flex items-center border border-border focus-within:border-white/60 transition-colors">
              <span className="text-[10px] text-muted-foreground pl-1.5">$</span>
              <input
                type="text"
                inputMode="numeric"
                value={amountInput}
                onChange={(e) => setAmountInput(e.target.value)}
                onBlur={commitAmount}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                }}
                className="w-28 text-[10px] bg-black px-1 py-0.5 font-mono text-white focus:outline-none"
                placeholder="e.g. 1,000,000"
              />
            </div>
            <span className="editorial-label text-[7.5px] text-muted-foreground tracking-widest uppercase">
              {hasMoney ? "shown in dollars" : "leave blank for %"}
            </span>
          </section>
        )}

        {/* ── Outcome: baseline vs scenario ── */}
        {proj && (
          <section className="grid grid-cols-2 gap-3 border-b border-border pb-4">
            <div className="border border-border p-3">
              <div className="editorial-label text-[7.5px] text-muted-foreground tracking-widest uppercase mb-1">Baseline</div>
              {hasMoney ? (
                <>
                  <div className="font-serif text-xl text-gray-300 nums-tabular">{usd(proj.baseline.endValue)}</div>
                  <div className="editorial-label text-[7.5px] text-muted-foreground mt-1 nums-tabular">
                    {pct(proj.baseline.expectedReturnPct)} · p5 {usd(proj.baseline.p5Value, true)} · p95 {usd(proj.baseline.p95Value, true)}
                  </div>
                </>
              ) : (
                <>
                  <div className="font-serif text-xl text-gray-300 nums-tabular">{pct(proj.baseline.expectedReturnPct)}</div>
                  <div className="editorial-label text-[7.5px] text-muted-foreground mt-1 nums-tabular">
                    p5 {pct(proj.baseline.p5Pct)} · p95 {pct(proj.baseline.p95Pct)}
                  </div>
                </>
              )}
            </div>
            <div className={`border p-3 ${scenUp ? "border-white/50 bg-white/[0.04]" : "border-muted-foreground/40 bg-muted/10"}`}>
              <div className="editorial-label text-[7.5px] text-muted-foreground tracking-widest uppercase mb-1">
                Scenario {proj.scenario.deltaPct !== undefined && (
                  <span className="text-white">({pct(proj.scenario.deltaPct)} vs base)</span>
                )}
              </div>
              {hasMoney ? (
                <>
                  <div className="font-serif text-xl text-white nums-tabular">{usd(proj.scenario.endValue)}</div>
                  <div className="editorial-label text-[7.5px] text-muted-foreground mt-1 nums-tabular">
                    {pct(proj.scenario.expectedReturnPct)} · p5 {usd(proj.scenario.p5Value, true)} · p95 {usd(proj.scenario.p95Value, true)}
                  </div>
                </>
              ) : (
                <>
                  <div className="font-serif text-xl text-white nums-tabular">{pct(proj.scenario.expectedReturnPct)}</div>
                  <div className="editorial-label text-[7.5px] text-muted-foreground mt-1 nums-tabular">
                    p5 {pct(proj.scenario.p5Pct)} · p95 {pct(proj.scenario.p95Pct)}
                  </div>
                </>
              )}
            </div>
          </section>
        )}

        {/* ── Tune: editable horizon + overall drift, instant re-run ── */}
        {canTune && (
          <section className="border-b border-border pb-4">
            <div className="flex items-center gap-2 mb-3">
              <SlidersHorizontal className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
              <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Tune Assumptions</span>
              {recomputing && <Loader2 className="w-3 h-3 text-muted-foreground animate-spin" strokeWidth={1.5} />}
              {dirty && !recomputing && (
                <button
                  onClick={reset}
                  className="ml-auto flex items-center gap-1 editorial-label text-[7.5px] text-muted-foreground hover:text-white tracking-widest uppercase transition-colors"
                >
                  <RotateCcw className="w-2.5 h-2.5" strokeWidth={1.5} /> reset
                </button>
              )}
            </div>

            {/* Horizon */}
            <div className="mb-3">
              <div className="flex items-center justify-between mb-1.5">
                <label className="editorial-label text-[8px] text-muted-foreground tracking-widest uppercase">Horizon</label>
                <span className="editorial-label text-[8px] text-white nums-tabular">{horizon}d</span>
              </div>
              <input
                type="range"
                min={21}
                max={1260}
                step={21}
                value={horizon}
                onChange={(e) => onHorizon(Number(e.target.value))}
                className="w-full accent-white h-1 cursor-pointer"
              />
            </div>

            {/* Overall drift */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="editorial-label text-[8px] text-muted-foreground tracking-widest uppercase">Net drift / yr</label>
                <span className="editorial-label text-[8px] text-white nums-tabular">{pct(drift)}</span>
              </div>
              <input
                type="range"
                min={-40}
                max={40}
                step={0.5}
                value={drift}
                onChange={(e) => onDrift(Number(e.target.value))}
                className="w-full accent-white h-1 cursor-pointer"
              />
            </div>

            {notice && (
              <p className="mt-3 editorial-label text-[8px] text-amber-300/80 leading-relaxed">{notice}</p>
            )}
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
              <span className="editorial-label text-[8px] text-white ml-auto nums-tabular">net {pct(drift)} / yr</span>
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
                      {canTune ? (
                        <div className="flex items-center gap-1 shrink-0">
                          <input
                            type="number"
                            step={0.5}
                            value={impacts[i] ?? 0}
                            onChange={(e) => onImpact(i, Number(e.target.value))}
                            className="w-14 bg-transparent border border-border px-1 py-0.5 text-right editorial-label text-[8px] text-white nums-tabular focus:outline-none focus:border-white transition-colors"
                          />
                          <span className="editorial-label text-[8px] text-muted-foreground">%</span>
                        </div>
                      ) : (
                        a.impactPct !== undefined && (
                          <span className="editorial-label text-[8px] text-muted-foreground nums-tabular shrink-0">{pct(a.impactPct)}</span>
                        )
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
