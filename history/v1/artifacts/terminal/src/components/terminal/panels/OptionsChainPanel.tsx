import React, { useMemo, useState } from "react";

interface OptionsChainPanelProps {
  data: any;
}

const PAGE_SIZE = 12;

function fmtNum(n: number): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function heat(volume: number, max: number): string {
  if (!max) return "transparent";
  const t = Math.min(1, volume / max);
  // subtle white wash that intensifies with activity
  return `rgba(255,255,255,${(t * 0.14).toFixed(3)})`;
}

export function OptionsChainPanel({ data }: OptionsChainPanelProps) {
  const expiries: string[] = data.expiries || [];
  const [selected, setSelected] = useState<string>(
    data.selectedExpiry && expiries.includes(data.selectedExpiry)
      ? data.selectedExpiry
      : expiries[0]
  );
  const [page, setPage] = useState(0);

  const chain = useMemo(
    () => (data.chains || []).find((c: any) => c.label === selected) || (data.chains || [])[0],
    [data.chains, selected]
  );

  const rows: any[] = chain?.rows || [];
  const atmStrike = data.atmStrike;

  // Center pagination on the at-the-money strike on first render of a chain.
  const atmIndex = useMemo(() => {
    let idx = 0;
    let best = Infinity;
    rows.forEach((r, i) => {
      const d = Math.abs(r.strike - atmStrike);
      if (d < best) {
        best = d;
        idx = i;
      }
    });
    return idx;
  }, [rows, atmStrike]);

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));

  // When the user switches expiry, jump to the page containing the ATM strike.
  React.useEffect(() => {
    setPage(Math.min(totalPages - 1, Math.floor(atmIndex / PAGE_SIZE)));
  }, [selected, atmIndex, totalPages]);

  const start = page * PAGE_SIZE;
  const visible = rows.slice(start, start + PAGE_SIZE);

  const maxVol = useMemo(() => {
    let m = 0;
    for (const r of rows) m = Math.max(m, r.callVolume, r.putVolume);
    return m;
  }, [rows]);

  return (
    <div className="flex flex-col h-full w-full gap-2">
      {/* Header */}
      <div className="flex justify-between items-baseline shrink-0">
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-bold">{data.symbol}</span>
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
            Options Chain
          </span>
        </div>
        <div className="text-right">
          <span className="text-xs text-muted-foreground mr-1">Spot</span>
          <span className="text-sm font-bold font-mono">${data.underlyingPrice.toFixed(2)}</span>
        </div>
      </div>

      {/* Expiry selector */}
      <div className="flex flex-wrap gap-1 shrink-0">
        {expiries.map((exp) => {
          const active = exp === selected;
          return (
            <button
              key={exp}
              onClick={() => setSelected(exp)}
              className={`px-2 py-0.5 text-[10px] font-mono border rounded-sm transition-colors ${
                active
                  ? "bg-white text-black border-white"
                  : "border-border text-muted-foreground hover:text-white hover:border-white/40"
              }`}
            >
              {exp}
            </button>
          );
        })}
        {chain?.daysToExpiry !== undefined && (
          <span className="ml-auto self-center text-[9px] text-muted-foreground font-mono">
            {chain.daysToExpiry}d to expiry
          </span>
        )}
      </div>

      {/* Calls | Strike | Puts table */}
      <div className="flex-1 overflow-auto min-h-0">
        <table className="w-full text-[10px] border-collapse font-mono">
          <thead className="sticky top-0 bg-black z-10">
            <tr className="text-muted-foreground">
              <th colSpan={6} className="text-center py-1 border-b border-border/60 uppercase tracking-wider text-white/70 font-semibold">
                Calls
              </th>
              <th className="border-b border-border/60" />
              <th colSpan={6} className="text-center py-1 border-b border-border/60 uppercase tracking-wider text-white/70 font-semibold">
                Puts
              </th>
            </tr>
            <tr className="text-muted-foreground text-[9px] uppercase">
              <th className="text-right font-normal px-1 py-0.5">OI</th>
              <th className="text-right font-normal px-1 py-0.5">Vol</th>
              <th className="text-right font-normal px-1 py-0.5">IV</th>
              <th className="text-right font-normal px-1 py-0.5">Last</th>
              <th className="text-right font-normal px-1 py-0.5">Bid</th>
              <th className="text-right font-normal px-1 py-0.5">Ask</th>
              <th className="text-center font-semibold px-1 py-0.5 text-white">Strike</th>
              <th className="text-right font-normal px-1 py-0.5">Bid</th>
              <th className="text-right font-normal px-1 py-0.5">Ask</th>
              <th className="text-right font-normal px-1 py-0.5">Last</th>
              <th className="text-right font-normal px-1 py-0.5">IV</th>
              <th className="text-right font-normal px-1 py-0.5">Vol</th>
              <th className="text-right font-normal px-1 py-0.5">OI</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => {
              const isAtm = r.strike === atmStrike;
              const callItm = r.strike < data.underlyingPrice;
              const putItm = r.strike > data.underlyingPrice;
              return (
                <tr
                  key={r.strike}
                  className={`border-b border-border/30 ${isAtm ? "outline outline-1 outline-white/40" : ""}`}
                >
                  {/* Calls */}
                  <td className="text-right px-1 py-0.5 text-muted-foreground">{fmtNum(r.callOi)}</td>
                  <td className="text-right px-1 py-0.5 text-muted-foreground" style={{ backgroundColor: heat(r.callVolume, maxVol) }}>
                    {fmtNum(r.callVolume)}
                  </td>
                  <td className="text-right px-1 py-0.5 text-muted-foreground">{r.callIv.toFixed(1)}</td>
                  <td className="text-right px-1 py-0.5">{r.callLast.toFixed(2)}</td>
                  <td className={`text-right px-1 py-0.5 ${callItm ? "text-white" : "text-muted-foreground"}`}>{r.callBid.toFixed(2)}</td>
                  <td className={`text-right px-1 py-0.5 ${callItm ? "text-white" : "text-muted-foreground"}`}>{r.callAsk.toFixed(2)}</td>
                  {/* Strike */}
                  <td className={`text-center px-1 py-0.5 font-bold ${isAtm ? "text-white" : "text-white/80"}`}>
                    {r.strike % 1 === 0 ? r.strike.toFixed(0) : r.strike.toFixed(1)}
                    {isAtm && <span className="ml-1 text-[8px] text-white/60">ATM</span>}
                  </td>
                  {/* Puts */}
                  <td className={`text-right px-1 py-0.5 ${putItm ? "text-white" : "text-muted-foreground"}`}>{r.putBid.toFixed(2)}</td>
                  <td className={`text-right px-1 py-0.5 ${putItm ? "text-white" : "text-muted-foreground"}`}>{r.putAsk.toFixed(2)}</td>
                  <td className="text-right px-1 py-0.5">{r.putLast.toFixed(2)}</td>
                  <td className="text-right px-1 py-0.5 text-muted-foreground">{r.putIv.toFixed(1)}</td>
                  <td className="text-right px-1 py-0.5 text-muted-foreground" style={{ backgroundColor: heat(r.putVolume, maxVol) }}>
                    {fmtNum(r.putVolume)}
                  </td>
                  <td className="text-right px-1 py-0.5 text-muted-foreground">{fmtNum(r.putOi)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination footer */}
      <div className="flex items-center justify-between shrink-0 text-[10px] text-muted-foreground border-t border-border pt-1">
        <button
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={page === 0}
          className="px-2 py-0.5 border border-border rounded-sm disabled:opacity-30 hover:text-white hover:border-white/40 transition-colors"
        >
          ← Lower strikes
        </button>
        <span className="font-mono">
          Strikes {start + 1}–{Math.min(start + PAGE_SIZE, rows.length)} of {rows.length}
        </span>
        <button
          onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          disabled={page >= totalPages - 1}
          className="px-2 py-0.5 border border-border rounded-sm disabled:opacity-30 hover:text-white hover:border-white/40 transition-colors"
        >
          Higher strikes →
        </button>
      </div>
    </div>
  );
}
