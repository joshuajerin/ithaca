// @ts-nocheck
import React, { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

interface OptionsScreenerPanelProps {
  data: any;
  onRefine?: (params: Record<string, unknown>) => void;
  pending?: boolean;
}

const PAGE_SIZE = 14;

const RANK_OPTIONS: { value: string; label: string }[] = [
  { value: "iv", label: "Highest IV" },
  { value: "volume", label: "Top Volume" },
  { value: "oi", label: "Top OI" },
  { value: "cheap", label: "Cheapest" },
  { value: "skew", label: "Widest Skew" },
];
const TYPE_OPTIONS = ["all", "call", "put"];
const MONEYNESS_OPTIONS = ["all", "otm", "itm", "atm"];

function fmtNum(n: number): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function heat(volume: number, max: number): string {
  if (!max) return "transparent";
  const t = Math.min(1, volume / max);
  return `rgba(255,255,255,${(t * 0.14).toFixed(3)})`;
}

// Numeric threshold input that commits on blur / Enter (not per keystroke) so a
// refine only fires once the user finishes typing a value.
function NumInput({
  label,
  value,
  placeholder,
  pending,
  onCommit,
}: {
  label: string;
  value: number | string | null | undefined;
  placeholder?: string;
  pending?: boolean;
  onCommit: (v: number | "") => void;
}) {
  const [v, setV] = useState<string>(value === null || value === undefined ? "" : String(value));
  React.useEffect(() => {
    setV(value === null || value === undefined ? "" : String(value));
  }, [value]);
  const commit = () => {
    const next = v.trim() === "" ? "" : Number(v);
    if (next !== "" && Number.isNaN(next as number)) return;
    onCommit(next as number | "");
  };
  return (
    <label className="flex items-center gap-1">
      <span className="text-[8px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        value={v}
        placeholder={placeholder}
        disabled={pending}
        onChange={(e) => setV(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        className="w-12 bg-transparent border border-border rounded-sm px-1 py-0.5 text-[9px] font-mono text-white text-right focus:border-white/40 outline-none disabled:opacity-50"
      />
    </label>
  );
}

export function OptionsScreenerPanel({ data, onRefine, pending }: OptionsScreenerPanelProps) {
  const rows: any[] = data.rows || [];
  const filters = data.filters || {};
  const [page, setPage] = useState(0);

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  React.useEffect(() => {
    setPage(0);
  }, [data]);

  const start = page * PAGE_SIZE;
  const visible = rows.slice(start, start + PAGE_SIZE);

  const maxVol = useMemo(() => {
    let m = 0;
    for (const r of rows) m = Math.max(m, r.volume);
    return m;
  }, [rows]);

  const rankBy: string = data.rankBy || "iv";

  // Build a full params payload so a control change re-runs the screen
  // deterministically without dropping the rest of the filter state.
  const emit = (patch: Record<string, unknown>) => {
    if (!onRefine) return;
    onRefine({
      sector: filters.sector,
      country: filters.country,
      exchange: filters.exchange,
      optionType: filters.optionType ?? "all",
      moneyness: filters.moneyness ?? "all",
      ivMin: filters.ivMin ?? 0,
      ivMax: filters.ivMax ?? "",
      dteMin: filters.dteMin ?? 0,
      dteMax: filters.dteMax ?? "",
      volumeMin: filters.volumeMin ?? 0,
      oiMin: filters.oiMin ?? 0,
      rankBy,
      limit: filters.limit ?? 40,
      ...patch,
    });
  };

  const live = data.source === "live";

  const Pill = ({
    active,
    onClick,
    children,
  }: {
    active: boolean;
    onClick: () => void;
    children: React.ReactNode;
  }) => (
    <button
      onClick={onClick}
      disabled={pending}
      className={`px-1.5 py-0.5 text-[9px] uppercase tracking-wider rounded-sm border transition-colors disabled:opacity-50 ${
        active
          ? "border-white/60 text-white bg-white/10"
          : "border-border text-muted-foreground hover:text-white hover:border-white/40"
      }`}
    >
      {children}
    </button>
  );

  return (
    <div className="flex flex-col h-full w-full gap-2">
      {/* Header */}
      <div className="flex justify-between items-baseline shrink-0">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-bold uppercase tracking-wider">Options Screener</span>
          <span className="text-[10px] text-muted-foreground">{data.universeLabel}</span>
        </div>
        <div className="text-right text-[10px] text-muted-foreground font-mono">
          {data.shown} of {data.matched} matches · {data.scanned} names
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-col gap-1.5 shrink-0 border-b border-border pb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground w-10">Rank</span>
          {RANK_OPTIONS.map((o) => (
            <Pill key={o.value} active={rankBy === o.value} onClick={() => emit({ rankBy: o.value })}>
              {o.label}
            </Pill>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground w-10">Type</span>
          {TYPE_OPTIONS.map((t) => (
            <Pill
              key={t}
              active={(filters.optionType ?? "all") === t}
              onClick={() => emit({ optionType: t })}
            >
              {t}
            </Pill>
          ))}
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground ml-2">Moneyness</span>
          {MONEYNESS_OPTIONS.map((m) => (
            <Pill
              key={m}
              active={(filters.moneyness ?? "all") === m}
              onClick={() => emit({ moneyness: m })}
            >
              {m}
            </Pill>
          ))}
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground w-10">IV%</span>
          <NumInput label="min" value={filters.ivMin ?? 0} placeholder="0" pending={pending} onCommit={(v) => emit({ ivMin: v === "" ? 0 : v })} />
          <NumInput label="max" value={filters.ivMax ?? ""} placeholder="∞" pending={pending} onCommit={(v) => emit({ ivMax: v })} />
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground ml-1">DTE</span>
          <NumInput label="min" value={filters.dteMin ?? 0} placeholder="0" pending={pending} onCommit={(v) => emit({ dteMin: v === "" ? 0 : v })} />
          <NumInput label="max" value={filters.dteMax ?? ""} placeholder="∞" pending={pending} onCommit={(v) => emit({ dteMax: v })} />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground w-10">Min</span>
          <NumInput label="vol" value={filters.volumeMin ?? 0} placeholder="0" pending={pending} onCommit={(v) => emit({ volumeMin: v === "" ? 0 : v })} />
          <NumInput label="oi" value={filters.oiMin ?? 0} placeholder="0" pending={pending} onCommit={(v) => emit({ oiMin: v === "" ? 0 : v })} />
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground ml-1">Rows</span>
          <NumInput label="limit" value={filters.limit ?? 40} placeholder="40" pending={pending} onCommit={(v) => emit({ limit: v === "" ? 40 : v })} />
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto relative min-h-0">
        {pending && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 pointer-events-none z-10">
            <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.25} />
          </div>
        )}
        {rows.length === 0 ? (
          <div className="w-full h-full flex items-center justify-center text-muted-foreground text-xs p-4 text-center">
            No contracts match these filters. Loosen the IV, expiry, or moneyness bands.
          </div>
        ) : (
          <table className="w-full text-[10px] font-mono border-collapse">
            <thead className="sticky top-0 bg-black">
              <tr className="text-muted-foreground uppercase tracking-wider text-[8px]">
                <th className="text-left px-1 py-1">#</th>
                <th className="text-left px-1 py-1">Symbol</th>
                <th className="text-center px-1 py-1">Exp</th>
                <th className="text-right px-1 py-1">DTE</th>
                <th className="text-right px-1 py-1">Strike</th>
                <th className="text-center px-1 py-1">Type</th>
                <th className={`text-right px-1 py-1 ${rankBy === "iv" ? "text-white" : ""}`}>IV%</th>
                <th className={`text-right px-1 py-1 ${rankBy === "skew" ? "text-white" : ""}`}>Skew</th>
                <th className="text-right px-1 py-1">Mny%</th>
                <th className="text-right px-1 py-1">Last</th>
                <th className={`text-right px-1 py-1 ${rankBy === "cheap" ? "text-white" : ""}`}>Mid</th>
                <th className={`text-right px-1 py-1 ${rankBy === "volume" ? "text-white" : ""}`}>Vol</th>
                <th className={`text-right px-1 py-1 ${rankBy === "oi" ? "text-white" : ""}`}>OI</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r, i) => (
                <tr key={`${r.symbol}-${r.expiry}-${r.strike}-${r.type}`} className="border-t border-border/40 hover:bg-white/5">
                  <td className="text-left px-1 py-0.5 text-muted-foreground">{start + i + 1}</td>
                  <td className="text-left px-1 py-0.5 text-white font-semibold">
                    {r.symbol}
                    {r.source && r.source !== "live" && (
                      <span className="ml-1 text-[7px] text-muted-foreground/70 uppercase">{r.source}</span>
                    )}
                  </td>
                  <td className="text-center px-1 py-0.5 text-muted-foreground">{r.expiry}</td>
                  <td className="text-right px-1 py-0.5 text-muted-foreground">{r.dte}</td>
                  <td className="text-right px-1 py-0.5">{r.strike}</td>
                  <td className={`text-center px-1 py-0.5 uppercase ${r.type === "call" ? "text-white" : "text-gray-400"}`}>
                    {r.type === "call" ? "C" : "P"}
                  </td>
                  <td className={`text-right px-1 py-0.5 ${rankBy === "iv" ? "text-white" : ""}`}>{r.iv.toFixed(1)}</td>
                  <td className={`text-right px-1 py-0.5 ${r.skew >= 0 ? "text-muted-foreground" : "text-gray-500"} ${rankBy === "skew" ? "text-white" : ""}`}>
                    {r.skew >= 0 ? "+" : ""}
                    {r.skew.toFixed(1)}
                  </td>
                  <td className="text-right px-1 py-0.5 text-muted-foreground">
                    {r.moneyness >= 0 ? "+" : ""}
                    {r.moneyness.toFixed(1)}
                  </td>
                  <td className="text-right px-1 py-0.5 text-muted-foreground">{r.last.toFixed(2)}</td>
                  <td className={`text-right px-1 py-0.5 ${rankBy === "cheap" ? "text-white" : ""}`}>{r.mid.toFixed(2)}</td>
                  <td
                    className={`text-right px-1 py-0.5 text-muted-foreground ${rankBy === "volume" ? "text-white" : ""}`}
                    style={{ backgroundColor: heat(r.volume, maxVol) }}
                  >
                    {fmtNum(r.volume)}
                  </td>
                  <td className={`text-right px-1 py-0.5 text-muted-foreground ${rankBy === "oi" ? "text-white" : ""}`}>
                    {fmtNum(r.oi)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between shrink-0 text-[10px] text-muted-foreground border-t border-border pt-1">
        <button
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={page === 0}
          className="px-2 py-0.5 border border-border rounded-sm disabled:opacity-30 hover:text-white hover:border-white/40 transition-colors"
        >
          ← Prev
        </button>
        <span className="font-mono">
          {rows.length > 0 ? `${start + 1}–${Math.min(start + PAGE_SIZE, rows.length)} of ${rows.length}` : "—"}
          {" · "}
          <span className={live ? "text-white/70" : ""}>{live ? "live" : "reference"}</span>
          {data.asOf ? ` · ${data.asOf}` : ""}
        </span>
        <button
          onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          disabled={page >= totalPages - 1}
          className="px-2 py-0.5 border border-border rounded-sm disabled:opacity-30 hover:text-white hover:border-white/40 transition-colors"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
