import React from "react";

// Generic, schema-agnostic fallback renderer for an AI-generated panel whose
// dedicated component hasn't been picked up yet (e.g. before the dev server's
// HMR registers the new file). Renders the data dict in a readable, on-brand way.
function renderValue(value: any): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-muted-foreground">—</span>;
  if (typeof value === "number") return <span className="tabular-nums">{value.toLocaleString()}</span>;
  if (typeof value === "boolean") return <span>{value ? "yes" : "no"}</span>;
  if (typeof value === "string") return <span>{value}</span>;
  if (Array.isArray(value)) {
    return (
      <div className="flex flex-col gap-1">
        {value.slice(0, 12).map((v, i) => (
          <div key={i} className="text-xs">
            {typeof v === "object" && v !== null ? (
              <span className="text-muted-foreground">
                {Object.entries(v)
                  .slice(0, 4)
                  .map(([k, val]) => `${k}: ${val}`)
                  .join("  ·  ")}
              </span>
            ) : (
              String(v)
            )}
          </div>
        ))}
        {value.length > 12 && (
          <span className="editorial-label text-[8px] text-muted-foreground">+{value.length - 12} more</span>
        )}
      </div>
    );
  }
  if (typeof value === "object") {
    return (
      <div className="flex flex-col gap-1.5">
        {Object.entries(value)
          .slice(0, 12)
          .map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 text-xs">
              <span className="text-muted-foreground">{k}</span>
              <span className="text-right truncate">{renderValue(v)}</span>
            </div>
          ))}
      </div>
    );
  }
  return <span>{String(value)}</span>;
}

export function GeneratedPanel({ data }: { data: any }) {
  if (!data || typeof data !== "object") {
    return <div className="p-2 text-xs text-muted-foreground">No data.</div>;
  }
  return (
    <div className="flex flex-col gap-3 h-full overflow-auto text-white">
      {Object.entries(data).map(([key, value]) => (
        <div key={key} className="flex flex-col gap-1">
          <span className="editorial-label text-[8.5px] text-muted-foreground">{key.replace(/_/g, " ")}</span>
          <div className="font-serif text-sm leading-snug">{renderValue(value)}</div>
        </div>
      ))}
    </div>
  );
}
