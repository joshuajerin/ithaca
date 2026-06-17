import React from "react";

export interface DataCoverage {
  windowStart?: string | null;
  windowEnd?: string | null;
  kind?: string;
  pointInTime?: boolean;
  survivorshipSafe?: boolean;
  status?: string | null;
  listedAt?: string | null;
  delistedAt?: string | null;
  priceBasis?: string;
  delistedInWindow?: number;
  delistedIncluded?: string[];
  delistedExcluded?: string[];
  pitApplied?: number;
  pitMissing?: number;
  pitCoverage?: {
    covered?: number | null;
    total?: number | null;
    periodRange?: { min?: string | null; max?: string | null } | null;
  } | null;
  notes?: string[];
}

function Pill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`text-[8px] uppercase tracking-widest px-1.5 py-0.5 border whitespace-nowrap ${
        ok ? "border-emerald-500/40 text-emerald-400/90" : "border-amber-500/40 text-amber-400/90"
      }`}
    >
      {label}
    </span>
  );
}

/**
 * Compact "data integrity" strip: point-in-time vs best-effort-current,
 * survivorship status, delisted/PIT counts and an honest one-line caveat.
 * Renders nothing when no coverage block is present (older payloads).
 */
export function CoverageBadge({ coverage }: { coverage?: DataCoverage | null }) {
  if (!coverage) return null;
  const c = coverage;
  const notes = c.notes ?? [];
  const title = notes.join("\n");
  const pit = c.pitCoverage;
  const hasPitCov =
    pit && typeof pit.covered === "number" && typeof pit.total === "number" && pit.total > 0;

  return (
    <div
      className="shrink-0 border border-border/40 bg-white/[0.02] px-2 py-1 flex flex-wrap items-center gap-1.5"
      title={title || undefined}
    >
      <span className="text-[8px] text-muted-foreground uppercase tracking-widest mr-0.5">
        Data integrity
      </span>
      {typeof c.pointInTime === "boolean" && (
        <Pill ok={c.pointInTime} label={c.pointInTime ? "Point-in-time" : "Best-effort current"} />
      )}
      {typeof c.survivorshipSafe === "boolean" && (
        <Pill ok={c.survivorshipSafe} label={c.survivorshipSafe ? "Survivorship-safe" : "Survivor-only"} />
      )}
      {c.status === "delisted" && (
        <span className="text-[8px] uppercase tracking-widest px-1.5 py-0.5 border border-sky-500/40 text-sky-400/90 whitespace-nowrap">
          Delisted{c.delistedAt ? ` ${c.delistedAt}` : ""}
        </span>
      )}
      {typeof c.delistedInWindow === "number" && c.delistedInWindow > 0 && (
        <span className="text-[8px] text-muted-foreground font-mono">
          {c.delistedInWindow} delisted in window
        </span>
      )}
      {hasPitCov && (
        <span className="text-[8px] text-muted-foreground font-mono">
          PIT fundamentals {pit!.covered}/{pit!.total}
        </span>
      )}
      {notes.length > 0 && (
        <span className="text-[8px] text-muted-foreground/70 italic truncate max-w-full">
          {notes[0]}
        </span>
      )}
    </div>
  );
}
