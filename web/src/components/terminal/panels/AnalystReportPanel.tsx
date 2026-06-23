// @ts-nocheck
import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowUpRight, ArrowDownRight, ArrowRight, TrendingUp, AlertTriangle, Calendar, Scale, Flag } from "lucide-react";

interface Item {
  title: string;
  detail: string;
}

interface Figure {
  label: string;
  value: string;
}

interface AnalystReportData {
  scope: string;
  scopeType: "symbol" | "sector" | "dashboard";
  symbol?: string | null;
  sector?: string | null;
  headline: string;
  stance: "bullish" | "bearish" | "neutral";
  conviction: number;
  thesis: string;
  drivers: Item[];
  risks: Item[];
  catalysts: Item[];
  valuation: string;
  call: string;
  figures: Figure[];
}

function StanceBadge({ stance }: { stance: "bullish" | "bearish" | "neutral" }) {
  const styles = {
    bullish: "border-white/50 text-white bg-white/8",
    bearish: "border-muted-foreground/50 text-muted-foreground bg-muted/10",
    neutral: "border-border text-gray-400 bg-transparent",
  };
  const icons = {
    bullish: <ArrowUpRight className="w-3 h-3" strokeWidth={2} />,
    bearish: <ArrowDownRight className="w-3 h-3" strokeWidth={2} />,
    neutral: <ArrowRight className="w-3 h-3" strokeWidth={2} />,
  };
  return (
    <span className={`flex items-center gap-1 px-2 py-0.5 border editorial-label text-[9px] shrink-0 uppercase tracking-widest ${styles[stance]}`}>
      {icons[stance]}
      {stance}
    </span>
  );
}

function Section({ icon, label, items }: { icon: React.ReactNode; label: string; items: Item[] }) {
  if (!items || items.length === 0) return null;
  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">{label}</span>
      </div>
      <div className="flex flex-col border-t border-border">
        {items.map((it, i) => (
          <div key={i} className="flex gap-3 py-2.5 border-b border-border last:border-b-0">
            <span className="editorial-label text-[8px] text-muted-foreground mt-0.5 nums-tabular shrink-0 w-4">
              {String(i + 1).padStart(2, "0")}
            </span>
            <div className="flex-1 min-w-0">
              <div className="font-serif text-sm text-white leading-tight mb-1">{it.title}</div>
              <p className="editorial-label text-[8.5px] text-muted-foreground leading-relaxed">{it.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function AnalystReportPanel({ data }: { data: AnalystReportData }) {
  const conviction = Math.max(0, Math.min(1, data.conviction ?? 0.5));
  const convPct = Math.round(conviction * 100);

  return (
    <ScrollArea className="h-full pr-1">
      <div className="flex flex-col gap-5 pb-2">

        {/* ── Header: stance, conviction, headline ── */}
        <section className="border-b border-border pb-4">
          <div className="flex items-center gap-3 mb-3">
            <StanceBadge stance={data.stance} />
            <div className="flex items-center gap-2 ml-auto">
              <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">Conviction</span>
              <div className="w-20 h-1 bg-border rounded-full overflow-hidden">
                <div className="h-full rounded-full bg-white" style={{ width: `${convPct}%` }} />
              </div>
              <span className="editorial-label text-[8.5px] text-white nums-tabular w-7 text-right">{convPct}%</span>
            </div>
          </div>
          <h2 className="font-serif text-lg text-white leading-snug">{data.headline}</h2>
        </section>

        {/* ── Grounding figures ── */}
        {data.figures && data.figures.length > 0 && (
          <section className="grid grid-cols-4 gap-x-4 gap-y-3 border-b border-border pb-4">
            {data.figures.map((f, i) => (
              <div key={i} className="flex flex-col gap-0.5">
                <span className="editorial-label text-[7px] text-muted-foreground tracking-widest uppercase">{f.label}</span>
                <span className="font-serif text-sm text-white nums-tabular">{f.value}</span>
              </div>
            ))}
          </section>
        )}

        {/* ── Thesis ── */}
        <section>
          <div className="flex items-center gap-2 mb-2">
            <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Thesis</span>
          </div>
          <p className="font-serif text-[13px] text-gray-200 leading-relaxed">{data.thesis}</p>
        </section>

        <Section
          icon={<TrendingUp className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />}
          label="Key Drivers"
          items={data.drivers}
        />
        <Section
          icon={<AlertTriangle className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />}
          label="Risks"
          items={data.risks}
        />
        <Section
          icon={<Calendar className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />}
          label="Catalysts"
          items={data.catalysts}
        />

        {/* ── Valuation ── */}
        {data.valuation && (
          <section>
            <div className="flex items-center gap-2 mb-2">
              <Scale className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
              <span className="editorial-label text-[8.5px] text-muted-foreground tracking-widest uppercase">Valuation</span>
            </div>
            <p className="editorial-label text-[9px] text-gray-300 leading-relaxed">{data.valuation}</p>
          </section>
        )}

        {/* ── The Call ── */}
        {data.call && (
          <section className="border border-border bg-white/[0.03] p-3">
            <div className="flex items-center gap-2 mb-2">
              <Flag className="w-3 h-3 text-white" strokeWidth={1.5} />
              <span className="editorial-label text-[8.5px] text-white tracking-widest uppercase">The Call</span>
            </div>
            <p className="font-serif text-[13px] text-white leading-relaxed">{data.call}</p>
          </section>
        )}

      </div>
    </ScrollArea>
  );
}
