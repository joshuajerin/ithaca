import React, { useEffect, useMemo, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FileText, ExternalLink, Search, X, ShieldAlert } from "lucide-react";

export interface FilingRow {
  form: string | null;
  rootForm?: string | null;
  filingDate: string | null;
  reportDate?: string | null;
  accession?: string | null;
  description?: string | null;
  size?: number | null;
  documentUrl?: string | null;
  indexUrl?: string | null;
  company?: string | null;
  cik?: string | null;
  fileType?: string | null;
}

interface FilingFormOption {
  form: string;
  count: number;
}

interface FilingsBrowserData {
  title: string;
  mode: "filings" | "search";
  symbol?: string | null;
  issuerName?: string | null;
  cik?: string | null;
  query?: string | null;
  forms?: string[];
  formOptions?: FilingFormOption[];
  filings: FilingRow[];
  count: number;
  total?: number;
  shown?: number;
  windowDays?: number | null;
  coverage?: string | null;
  feedSource?: string;
  asOf?: string | null;
  source?: string;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });
}

// Material forms get a coloured accent so the most-watched filings stand out.
function formTone(root: string): string {
  const f = root.toUpperCase();
  if (f === "10-K" || f === "20-F" || f === "40-F") return "text-amber-300 border-amber-400/30 bg-amber-400/5";
  if (f === "10-Q") return "text-sky-300 border-sky-400/30 bg-sky-400/5";
  if (f === "8-K" || f === "6-K") return "text-emerald-300 border-emerald-400/30 bg-emerald-400/5";
  if (f.startsWith("S-") || f.startsWith("424B")) return "text-violet-300 border-violet-400/30 bg-violet-400/5";
  if (f.startsWith("DEF") || f.startsWith("DEFA")) return "text-rose-300 border-rose-400/30 bg-rose-400/5";
  return "text-muted-foreground border-border bg-white/3";
}

export function FilingsBrowserPanel({
  data,
  onSearch,
  pending,
}: {
  data: FilingsBrowserData;
  onSearch?: (params: Record<string, unknown>) => void;
  pending?: boolean;
}) {
  const feed = data.feedSource ?? data.source;
  const unavailable = feed === "unavailable";
  const errored = feed === "error";
  const isSearch = data.mode === "search";

  const [selectedForm, setSelectedForm] = useState<string | null>(
    (data.forms && data.forms[0]) || null,
  );
  const [searchText, setSearchText] = useState<string>(data.query ?? "");

  // Reset the local controls whenever the panel is rebuilt for a new
  // subject/mode (symbol, query or mode change), so stale selection/search text
  // never leak across refines.
  const sig = `${data.mode}|${data.symbol ?? ""}|${data.query ?? ""}`;
  useEffect(() => {
    setSelectedForm((data.forms && data.forms[0]) || null);
    setSearchText(data.query ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig]);

  const rows = useMemo(() => {
    if (!selectedForm) return data.filings;
    return data.filings.filter(
      r => (r.rootForm || r.form || "").toUpperCase() === selectedForm.toUpperCase(),
    );
  }, [data.filings, selectedForm]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchText.trim();
    if (!q || !onSearch) return;
    const params: Record<string, unknown> = { query: q };
    if (data.symbol) params.symbol = data.symbol;
    onSearch(params);
  };

  const clearSearch = () => {
    setSearchText("");
    if (onSearch && data.symbol) onSearch({ symbol: data.symbol, query: "" });
  };

  const showFormChips = (data.formOptions?.length ?? 0) > 1;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
          <span className="text-xs font-bold uppercase truncate">{data.title}</span>
        </div>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider shrink-0 ml-2">
          {isSearch
            ? `${data.shown ?? data.count} / ${(data.total ?? 0).toLocaleString()}`
            : `${data.count} filings`}
        </span>
      </div>

      {/* Search box — full-text EDGAR search (also re-scopes the current ticker) */}
      {onSearch && (
        <form onSubmit={submitSearch} className="mb-2 shrink-0 flex items-center gap-1.5">
          <div className="relative flex-1">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" strokeWidth={1.8} />
            <input
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              placeholder={
                data.symbol
                  ? `Full-text search ${data.symbol} filings…`
                  : "Full-text search EDGAR filings…"
              }
              className="w-full bg-white/3 border border-border focus:border-gray-500 outline-none text-[11px] pl-7 pr-2 py-1 placeholder:text-muted-foreground/70"
            />
          </div>
          <button
            type="submit"
            disabled={pending || !searchText.trim()}
            className="text-[10px] uppercase tracking-widest px-2 py-1 border border-border text-muted-foreground hover:border-gray-500 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {pending ? "…" : "Search"}
          </button>
          {isSearch && data.symbol && (
            <button
              type="button"
              onClick={clearSearch}
              title="Back to filings list"
              className="text-muted-foreground hover:text-white p-1 border border-border"
            >
              <X className="w-3 h-3" strokeWidth={1.8} />
            </button>
          )}
        </form>
      )}

      {unavailable && (
        <div className="mb-2 shrink-0 flex items-center gap-2 border border-border bg-white/3 px-2.5 py-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.8} />
          <span className="text-[10px] text-muted-foreground leading-tight">
            {data.coverage || `No SEC filer found for ${data.symbol ?? "this name"}.`}
          </span>
        </div>
      )}
      {errored && (
        <div className="mb-2 shrink-0 flex items-center gap-2 border border-amber-400/40 bg-amber-400/5 px-2.5 py-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" strokeWidth={1.8} />
          <span className="text-[10px] text-amber-300 leading-tight">
            {data.coverage || "Couldn't reach SEC EDGAR right now — no filings to show."}
          </span>
        </div>
      )}

      {/* Form-type filter chips (client-side over the loaded list) */}
      {!unavailable && showFormChips && (
        <div className="flex gap-1 mb-2 shrink-0 flex-wrap">
          <button
            onClick={() => setSelectedForm(null)}
            className={`text-[10px] uppercase tracking-widest px-2 py-0.5 border transition-colors ${
              selectedForm === null
                ? "border-white text-white bg-white/10"
                : "border-border text-muted-foreground hover:border-gray-500"
            }`}
          >
            All
          </button>
          {data.formOptions!.map(opt => (
            <button
              key={opt.form}
              onClick={() => setSelectedForm(opt.form)}
              className={`text-[10px] uppercase tracking-widest px-2 py-0.5 border transition-colors ${
                selectedForm === opt.form
                  ? "border-white text-white bg-white/10"
                  : "border-border text-muted-foreground hover:border-gray-500"
              }`}
            >
              {opt.form} ({opt.count})
            </button>
          ))}
        </div>
      )}

      {/* Column header */}
      {!unavailable && (
        <div
          className={`grid ${
            isSearch
              ? "grid-cols-[0.9fr_0.7fr_0.7fr_1.6fr_0.4fr]"
              : "grid-cols-[0.8fr_0.7fr_0.7fr_1.6fr_0.4fr]"
          } gap-2 px-2 pb-1 shrink-0 text-[9px] text-muted-foreground uppercase tracking-wider border-b border-border`}
        >
          <span>Form</span>
          <span>Filed</span>
          <span>Period</span>
          <span>{isSearch ? "Filer / Doc" : "Description"}</span>
          <span className="text-right">Doc</span>
        </div>
      )}

      {/* Rows */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col">
          {rows.length === 0 && !unavailable && (
            <div className="text-xs text-muted-foreground px-2 py-4">
              {errored
                ? "No data available."
                : isSearch
                ? "No matching filings."
                : selectedForm
                ? `No ${selectedForm} filings in the recent set.`
                : "No filings found."}
            </div>
          )}
          {rows.map((r, i) => {
            const root = (r.rootForm || r.form || "—").toUpperCase();
            const link = r.documentUrl || r.indexUrl;
            return (
              <div
                key={`${r.accession}-${i}`}
                className={`grid ${
                  isSearch
                    ? "grid-cols-[0.9fr_0.7fr_0.7fr_1.6fr_0.4fr]"
                    : "grid-cols-[0.8fr_0.7fr_0.7fr_1.6fr_0.4fr]"
                } gap-2 items-center px-2 py-1.5 border-b border-border/40 hover:bg-white/3`}
              >
                <div>
                  <span className={`inline-block text-[9px] px-1 py-0.5 border uppercase ${formTone(root)}`}>
                    {r.form || root}
                  </span>
                </div>
                <div className="text-[10px] nums-tabular text-gray-200">{fmtDate(r.filingDate)}</div>
                <div className="text-[10px] nums-tabular text-gray-400">{fmtDate(r.reportDate)}</div>
                <div className="min-w-0 text-[10px] text-gray-300 truncate">
                  {isSearch ? (r.company || r.description || "—") : (r.description || "—")}
                </div>
                <div className="text-right">
                  {link ? (
                    <a
                      href={link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-end text-muted-foreground hover:text-white"
                      title={`View ${r.form || root} on SEC EDGAR`}
                    >
                      <ExternalLink className="w-3 h-3" strokeWidth={1.8} />
                    </a>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="shrink-0 pt-1.5 text-[9px] text-muted-foreground flex items-center justify-between border-t border-border/40 mt-1">
        <span>
          {selectedForm ? `${rows.length} ${selectedForm}` : `${rows.length} shown`}
          {isSearch && (data.total ?? 0) > (data.shown ?? data.count)
            ? ` · top ${data.shown ?? data.count} of ${(data.total ?? 0).toLocaleString()}`
            : ""}
        </span>
        {!unavailable && <span>SEC EDGAR</span>}
      </div>
    </div>
  );
}
