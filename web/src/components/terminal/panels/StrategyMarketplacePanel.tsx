// @ts-nocheck
import React, { useState, useMemo, useEffect, useCallback } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { Save, Check, Rocket, Loader2, AlertTriangle, ShieldAlert } from "lucide-react";

interface StatBlock {
  sharpe?: number;
  cagr?: number;
  totalReturn?: number;
  vol?: number;
  maxDD?: number;
  winRate?: number;
}

interface PreviewHolding {
  symbol?: string;
  name?: string;
  weight?: number;
}

interface TemplatePreview {
  stats?: StatBlock;
  benchStats?: StatBlock;
  curve?: { t: string; strategy: number; benchmark: number }[];
  drawdown?: { t: string; dd: number }[];
  holdings?: PreviewHolding[];
  universe?: string;
  universeSize?: number;
  included?: number;
  excluded?: number;
  source?: string;
  asOf?: string;
}

interface TemplateRecord {
  id: string;
  name: string;
  description?: string;
  category?: string;
  signal: string;
  signalLabel?: string;
  sector?: string | null;
  topN: number;
  capital: number;
  builtIn?: boolean;
}

interface SelectedTemplate extends TemplateRecord {
  preview?: TemplatePreview | null;
  previewError?: string | null;
}

interface SignalOption {
  id: string;
  label: string;
  desc?: string;
}

interface SectorOption {
  id: string;
  name: string;
}

interface MarketplaceData {
  templates: TemplateRecord[];
  selected: SelectedTemplate;
  signals: SignalOption[];
  sectors: SectorOption[];
  source?: string;
  asOf?: string;
}

function pct(n?: number, digits = 1): string {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return `${n >= 0 ? "" : ""}${n.toFixed(digits)}%`;
}

function num(n?: number, digits = 2): string {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function fmtCapital(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[8px] text-muted-foreground uppercase tracking-widest">{label}</span>
      <span className={`font-mono text-[13px] leading-tight ${tone ?? "text-white"}`}>{value}</span>
    </div>
  );
}

const inputCls =
  "w-full bg-black border border-border px-1.5 py-1 text-xs font-mono text-white focus:outline-none focus:border-white transition-colors disabled:opacity-50";

export function StrategyMarketplacePanel({
  data,
  sessionId,
  onRefine,
  pending,
}: {
  data: MarketplaceData;
  sessionId?: string;
  onRefine?: (params: Record<string, unknown>) => void;
  pending?: boolean;
}) {
  const sel = data.selected;
  const preview = sel?.preview ?? null;
  const stats = preview?.stats ?? {};
  const bench = preview?.benchStats ?? {};

  // Local control state mirrors the focused template; reset when the selected
  // template identity or its resolved params change (e.g. a server refine lands).
  const sig = sel?.signal ?? "momentum";
  const sectorVal = sel?.sector ?? "";
  const topN = sel?.topN ?? 10;
  const capital = sel?.capital ?? 1_000_000;

  const [draftTopN, setDraftTopN] = useState<number>(topN);
  const [draftCapital, setDraftCapital] = useState<number>(capital);

  const ctrlSig = useMemo(() => [sel?.id, sig, sectorVal, topN, capital].join("|"), [sel?.id, sig, sectorVal, topN, capital]);
  useEffect(() => {
    setDraftTopN(topN);
    setDraftCapital(capital);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctrlSig]);

  const [cloneState, setCloneState] = useState<{ busy: boolean; ok: boolean; msg: string | null; blocked: boolean }>({
    busy: false,
    ok: false,
    msg: null,
    blocked: false,
  });
  const [isNaming, setIsNaming] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveState, setSaveState] = useState<{ busy: boolean; ok: boolean; err: boolean }>({ busy: false, ok: false, err: false });

  const selectTemplate = useCallback(
    (id: string) => {
      if (!onRefine || id === sel?.id) return;
      onRefine({ templateId: id });
    },
    [onRefine, sel?.id],
  );

  const applyTweak = useCallback(
    (patch: Record<string, unknown>) => {
      if (!onRefine) return;
      onRefine({ templateId: sel?.id, signal: sig, sector: sectorVal, topN, capital, ...patch });
    },
    [onRefine, sel?.id, sig, sectorVal, topN, capital],
  );

  const handleClone = useCallback(async () => {
    setCloneState({ busy: true, ok: false, msg: null, blocked: false });
    try {
      const res = await fetch("/api/templates/clone", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          templateId: sel?.id,
          name: sel?.name,
          signal: sig,
          sector: sectorVal,
          topN,
          capital,
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json?.detail || "clone failed");
      if (json?.ok === false && json?.blocked) {
        setCloneState({ busy: false, ok: false, blocked: true, msg: json?.reason || "Blocked by compliance gate" });
        return;
      }
      const newName = json?.strategy?.name || sel?.name || "strategy";
      setCloneState({ busy: false, ok: true, blocked: false, msg: `Cloned “${newName}” to your strategy desk` });
      setTimeout(() => setCloneState(s => (s.ok ? { ...s, ok: false, msg: null } : s)), 4000);
    } catch (e) {
      setCloneState({ busy: false, ok: false, blocked: false, msg: e instanceof Error ? e.message : "Clone failed" });
      setTimeout(() => setCloneState(s => ({ ...s, msg: null })), 4000);
    }
  }, [sel?.id, sel?.name, sig, sectorVal, topN, capital]);

  const handleSave = useCallback(async () => {
    const name = saveName.trim();
    if (!name) {
      setIsNaming(false);
      return;
    }
    setSaveState({ busy: true, ok: false, err: false });
    try {
      const res = await fetch("/api/templates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          signal: sig,
          sector: sectorVal,
          topN,
          capital,
          category: "Saved",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setSaveState({ busy: false, ok: true, err: false });
      setIsNaming(false);
      setSaveName("");
      // Refresh the catalog so the new template appears in the list.
      if (onRefine) onRefine({ templateId: sel?.id });
      setTimeout(() => setSaveState(s => ({ ...s, ok: false })), 2000);
    } catch {
      setSaveState({ busy: false, ok: false, err: true });
      setTimeout(() => setSaveState(s => ({ ...s, err: false })), 2500);
    }
  }, [saveName, sig, sectorVal, topN, capital, onRefine, sel?.id]);

  const templates = data.templates ?? [];
  const builtIns = templates.filter(t => t.builtIn);
  const userTemplates = templates.filter(t => !t.builtIn);

  return (
    <div className="flex flex-col h-full text-xs">
      <div className="flex items-baseline gap-2 mb-2 shrink-0">
        <span className="editorial-label text-[8.5px] text-muted-foreground">Strategy Templates · Marketplace</span>
        {preview?.source && (
          <span className="ml-auto text-[9px] text-muted-foreground uppercase">
            {preview.source}{preview.asOf ? ` · ${preview.asOf}` : ""}
          </span>
        )}
      </div>

      <div className="flex-1 min-h-0 flex gap-3">
        {/* Catalog */}
        <div className="w-44 shrink-0 flex flex-col gap-1 overflow-y-auto pr-1">
          <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-0.5">Catalog</div>
          {builtIns.map(t => (
            <button
              key={t.id}
              type="button"
              onClick={() => selectTemplate(t.id)}
              className={`text-left border px-2 py-1.5 transition-colors ${
                t.id === sel?.id ? "border-white bg-white/5" : "border-border hover:border-white/40"
              }`}
            >
              <div className="font-serif text-[12px] leading-tight truncate">{t.name}</div>
              <div className="text-[8.5px] text-muted-foreground uppercase tracking-wider mt-0.5">{t.category}</div>
            </button>
          ))}
          {userTemplates.length > 0 && (
            <div className="text-[9px] text-muted-foreground uppercase tracking-widest mt-2 mb-0.5">Saved</div>
          )}
          {userTemplates.map(t => (
            <button
              key={t.id}
              type="button"
              onClick={() => selectTemplate(t.id)}
              className={`text-left border px-2 py-1.5 transition-colors ${
                t.id === sel?.id ? "border-white bg-white/5" : "border-border hover:border-white/40"
              }`}
            >
              <div className="font-serif text-[12px] leading-tight truncate">{t.name}</div>
              <div className="text-[8.5px] text-muted-foreground uppercase tracking-wider mt-0.5">{t.category || "Saved"}</div>
            </button>
          ))}
        </div>

        {/* Detail */}
        <div className="flex-1 min-w-0 flex flex-col gap-2 overflow-y-auto">
          <div className="shrink-0">
            <div className="font-serif text-base leading-none">{sel?.name}</div>
            <div className="text-[10px] text-muted-foreground mt-1 leading-snug">{sel?.description}</div>
          </div>

          {/* Tweak controls */}
          <div className="grid grid-cols-2 gap-2 shrink-0 border-y border-border py-2 relative">
            {pending && (
              <div className="absolute inset-0 bg-black/40 flex items-center justify-center z-10">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-white/60" strokeWidth={1.5} />
              </div>
            )}
            <div className="flex flex-col gap-0.5">
              <label className="text-[9px] text-muted-foreground uppercase tracking-wider">Signal</label>
              <select
                value={sig}
                onChange={e => applyTweak({ signal: e.target.value })}
                disabled={pending}
                className={inputCls}
              >
                {(data.signals ?? []).map(s => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-0.5">
              <label className="text-[9px] text-muted-foreground uppercase tracking-wider">Universe</label>
              <select
                value={sectorVal}
                onChange={e => applyTweak({ sector: e.target.value })}
                disabled={pending}
                className={inputCls}
              >
                {(data.sectors ?? []).map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-0.5">
              <label className="text-[9px] text-muted-foreground uppercase tracking-wider">Holdings (top N)</label>
              <input
                type="number"
                min={5}
                max={30}
                step={1}
                value={draftTopN}
                disabled={pending}
                onChange={e => setDraftTopN(parseInt(e.target.value) || topN)}
                onBlur={() => { if (draftTopN !== topN) applyTweak({ topN: draftTopN }); }}
                onKeyDown={e => { if (e.key === "Enter" && draftTopN !== topN) applyTweak({ topN: draftTopN }); }}
                className={inputCls}
              />
            </div>
            <div className="flex flex-col gap-0.5">
              <label className="text-[9px] text-muted-foreground uppercase tracking-wider">Capital ($)</label>
              <input
                type="number"
                min={0}
                step={100000}
                value={draftCapital}
                disabled={pending}
                onChange={e => setDraftCapital(parseFloat(e.target.value) || capital)}
                onBlur={() => { if (draftCapital !== capital) applyTweak({ capital: draftCapital }); }}
                onKeyDown={e => { if (e.key === "Enter" && draftCapital !== capital) applyTweak({ capital: draftCapital }); }}
                className={inputCls}
              />
            </div>
          </div>

          {/* Preview */}
          {sel?.previewError ? (
            <div className="flex-1 min-h-0 flex flex-col items-center justify-center text-muted-foreground gap-2 text-center p-4">
              <AlertTriangle className="w-4 h-4" strokeWidth={1.25} />
              <span className="text-[10px]">Preview unavailable: {sel.previewError}</span>
            </div>
          ) : preview ? (
            <>
              <div className="grid grid-cols-3 gap-2 shrink-0">
                <Stat label="Sharpe" value={num(stats.sharpe)} tone={(stats.sharpe ?? 0) >= 1 ? "text-emerald-400" : "text-white"} />
                <Stat label="CAGR" value={pct(stats.cagr)} tone={(stats.cagr ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"} />
                <Stat label="Max DD" value={pct(stats.maxDD)} tone="text-red-400" />
                <Stat label="Vol" value={pct(stats.vol)} />
                <Stat label="Total Ret" value={pct(stats.totalReturn)} tone={(stats.totalReturn ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"} />
                <Stat label="Bench CAGR" value={pct(bench.cagr)} tone="text-muted-foreground" />
              </div>

              {preview.curve && preview.curve.length > 1 && (
                <div className="flex-1 min-h-0 min-h-[120px]">
                  <div className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1">
                    Backtest · top-quantile vs benchmark
                  </div>
                  <ResponsiveContainer width="100%" height="85%">
                    <ComposedChart data={preview.curve} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="2 2" stroke="#1a1a1a" vertical={false} />
                      <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} minTickGap={40} />
                      <YAxis tick={{ fontSize: 8, fill: "#555" }} tickLine={false} axisLine={false} width={34} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#000", borderColor: "#333", borderRadius: 0, fontSize: 10 }}
                      />
                      <Line type="monotone" dataKey="strategy" name="Strategy" stroke="#fff" strokeWidth={1.5} dot={false} />
                      <Line type="monotone" dataKey="benchmark" name="Benchmark" stroke="#666" strokeWidth={1} dot={false} strokeDasharray="3 3" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}

              {preview.holdings && preview.holdings.length > 0 && (
                <div className="shrink-0">
                  <div className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1">
                    Top holdings · {sel?.topN} names{preview.universe ? ` · ${preview.universe}` : ""}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {preview.holdings.slice(0, 12).map(h => (
                      <span key={h.symbol} className="border border-border px-1.5 py-0.5 text-[9px] font-mono">
                        {h.symbol}
                        {h.weight !== undefined && (
                          <span className="text-muted-foreground"> {(h.weight as number).toFixed(0)}%</span>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="flex-1 min-h-0 flex items-center justify-center text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.25} />
            </div>
          )}

          {/* Actions */}
          <div className="shrink-0 border-t border-border pt-2 flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={handleClone}
              disabled={cloneState.busy || !preview}
              className="flex items-center gap-1.5 border border-white bg-white/5 hover:bg-white/10 text-white text-[10px] uppercase tracking-wider px-3 py-1.5 transition-colors disabled:opacity-50"
            >
              {cloneState.busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Rocket className="w-3 h-3" strokeWidth={1.5} />}
              Clone to strategy desk
            </button>

            {isNaming ? (
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  value={saveName}
                  onChange={e => setSaveName(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter") handleSave();
                    if (e.key === "Escape") { setIsNaming(false); setSaveName(""); }
                  }}
                  placeholder="Template name…"
                  autoFocus
                  disabled={saveState.busy}
                  className={`${inputCls} w-36`}
                />
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saveState.busy || !saveName.trim()}
                  className="shrink-0 text-muted-foreground hover:text-emerald-400 transition-colors disabled:opacity-50"
                  title="Confirm save"
                >
                  <Check className="w-3.5 h-3.5" strokeWidth={1.5} />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => { setSaveName(sel?.name ? `My ${sel.name}` : ""); setIsNaming(true); }}
                className="flex items-center gap-1.5 border border-border bg-black hover:border-white text-muted-foreground hover:text-white text-[10px] uppercase tracking-wider px-3 py-1.5 transition-colors"
              >
                <Save className="w-3 h-3" strokeWidth={1.5} /> Save as template
              </button>
            )}

            <span className="ml-auto text-[9px] uppercase tracking-wider text-muted-foreground">
              {fmtCapital(capital)} · {topN} names
            </span>
          </div>

          {/* Status line */}
          {(cloneState.msg || saveState.ok || saveState.err) && (
            <div className="shrink-0 text-[9px] uppercase tracking-wider flex items-center gap-1.5">
              {cloneState.blocked && <ShieldAlert className="w-3 h-3 text-amber-400" strokeWidth={1.5} />}
              {cloneState.msg && (
                <span className={cloneState.ok ? "text-emerald-400" : cloneState.blocked ? "text-amber-400" : "text-red-400"}>
                  {cloneState.msg}
                </span>
              )}
              {saveState.ok && <span className="text-emerald-400">Template saved</span>}
              {saveState.err && <span className="text-red-400">Save failed</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
