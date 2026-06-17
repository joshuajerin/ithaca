import React, { useCallback, useEffect, useState } from "react";
import { X, ShieldCheck, Loader2, AlertTriangle, RefreshCw, Lock } from "lucide-react";

interface AuditLogModalProps {
  open: boolean;
  onClose: () => void;
}

interface AuditEntry {
  id: string;
  at: string;
  category: string;
  action: string;
  target?: string | null;
  decision?: string | null;
  summary: string;
  actorUserId: string;
  actorName: string;
  detail?: Record<string, unknown>;
}

interface AuditActor {
  userId: string;
  name: string;
}

interface AuditResponse {
  entries: AuditEntry[];
  actors: AuditActor[];
  categories: string[];
}

function formatWhen(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso ?? "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// Each category gets a small accent so the trail scans quickly. The decision
// "blocked" always shows amber regardless of category.
const CATEGORY_LABEL: Record<string, string> = {
  compliance: "Compliance",
  trade: "Trade",
  strategy: "Strategy",
  config: "Config",
  dashboard: "Dashboard",
  alert: "Alert",
  feature: "Feature",
  auth: "Auth",
  admin: "Admin",
};

export function AuditLogModal({ open, onClose }: AuditLogModalProps) {
  const [data, setData] = useState<AuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [user, setUser] = useState("");
  const [category, setCategory] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (user) params.set("user", user);
      if (category) params.set("category", category);
      // The date inputs are local datetime; convert to ISO so the backend's
      // inclusive string comparison works against stored ISO timestamps.
      if (since) params.set("since", new Date(since).toISOString());
      if (until) params.set("until", new Date(until).toISOString());
      params.set("limit", "300");
      const res = await fetch(`/api/audit?${params.toString()}`);
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(json.detail || "Could not load the audit log.");
        return;
      }
      setData(json);
    } catch {
      setError("Network error.");
    } finally {
      setLoading(false);
    }
  }, [user, category, since, until]);

  useEffect(() => {
    if (open) {
      void load();
    } else {
      setUser("");
      setCategory("");
      setSince("");
      setUntil("");
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const entries = data?.entries ?? [];
  const actors = data?.actors ?? [];
  const categories = data?.categories ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl bg-black border border-border flex flex-col max-h-[88vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-border shrink-0">
          <div className="flex flex-col gap-1">
            <span className="editorial-label text-[8.5px] text-muted-foreground flex items-center gap-1.5">
              <ShieldCheck className="w-3 h-3" strokeWidth={1.5} /> Governance
            </span>
            <span className="font-serif text-xl leading-none">Firm Audit Trail</span>
            <span className="text-[10px] text-muted-foreground flex items-center gap-1.5 mt-1">
              <Lock className="w-2.5 h-2.5" strokeWidth={1.5} /> Append-only · who did what, when
            </span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-white transition-colors">
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        <div className="flex flex-wrap items-end gap-3 px-6 py-4 border-b border-border shrink-0">
          <label className="flex flex-col gap-1.5">
            <span className="editorial-label text-[8.5px] text-muted-foreground">User</span>
            <select
              value={user}
              onChange={(e) => setUser(e.target.value)}
              className="bg-black border border-border px-2.5 py-2 text-xs font-serif text-white focus:outline-none focus:border-white transition-colors min-w-[140px]"
            >
              <option value="">All users</option>
              {actors.map((a) => (
                <option key={a.userId} value={a.userId}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="editorial-label text-[8.5px] text-muted-foreground">Action type</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="bg-black border border-border px-2.5 py-2 text-xs font-serif text-white focus:outline-none focus:border-white transition-colors min-w-[130px]"
            >
              <option value="">All types</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABEL[c] ?? c}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="editorial-label text-[8.5px] text-muted-foreground">From</span>
            <input
              type="datetime-local"
              value={since}
              onChange={(e) => setSince(e.target.value)}
              className="bg-black border border-border px-2.5 py-2 text-xs font-serif text-white focus:outline-none focus:border-white transition-colors [color-scheme:dark]"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="editorial-label text-[8.5px] text-muted-foreground">To</span>
            <input
              type="datetime-local"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
              className="bg-black border border-border px-2.5 py-2 text-xs font-serif text-white focus:outline-none focus:border-white transition-colors [color-scheme:dark]"
            />
          </label>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="flex items-center gap-2 bg-white text-black px-4 py-2 editorial-label text-[9px] disabled:opacity-40 hover:bg-white/90 transition-colors"
          >
            {loading ? (
              <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} />
            ) : (
              <RefreshCw className="w-3 h-3" strokeWidth={2} />
            )}
            Apply
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-2 text-amber-400 text-xs border-b border-amber-400/30 bg-amber-400/5 px-6 py-2.5 shrink-0">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
            <span>{error}</span>
          </div>
        )}

        <div className="overflow-y-auto">
          {loading && entries.length === 0 ? (
            <div className="flex items-center gap-2 text-muted-foreground text-xs py-12 justify-center">
              <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} /> Loading the trail
            </div>
          ) : entries.length === 0 ? (
            <p className="text-sm text-muted-foreground/70 py-12 text-center font-serif">
              No audit entries match these filters yet.
            </p>
          ) : (
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 bg-black z-10">
                <tr className="border-b border-border">
                  <th className="editorial-label text-[8px] text-muted-foreground font-normal px-6 py-2.5">When</th>
                  <th className="editorial-label text-[8px] text-muted-foreground font-normal px-3 py-2.5">User</th>
                  <th className="editorial-label text-[8px] text-muted-foreground font-normal px-3 py-2.5">Type</th>
                  <th className="editorial-label text-[8px] text-muted-foreground font-normal px-3 py-2.5">Target</th>
                  <th className="editorial-label text-[8px] text-muted-foreground font-normal px-3 py-2.5">Detail</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => {
                  const blocked = (e.decision || "").toLowerCase() === "blocked";
                  return (
                    <tr key={e.id} className="border-b border-border/50 align-top hover:bg-white/[0.02]">
                      <td className="px-6 py-3 text-[11px] text-muted-foreground whitespace-nowrap tabular-nums">
                        {formatWhen(e.at)}
                      </td>
                      <td className="px-3 py-3 text-xs font-serif text-white whitespace-nowrap">
                        {e.actorName}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span
                          className={`editorial-label text-[8px] px-2 py-1 border ${
                            blocked
                              ? "border-amber-400/40 text-amber-400"
                              : "border-border text-muted-foreground"
                          }`}
                        >
                          {CATEGORY_LABEL[e.category] ?? e.category}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-[11px] text-white/80 whitespace-nowrap max-w-[160px] truncate">
                        {e.target || "—"}
                      </td>
                      <td className="px-3 py-3 text-xs text-white/90">
                        <span className="font-serif">{e.summary}</span>
                        <span className="block text-[9px] text-muted-foreground/70 mt-0.5 font-mono">
                          {e.action}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="px-6 py-3 border-t border-border text-[10px] text-muted-foreground shrink-0">
          {entries.length} {entries.length === 1 ? "entry" : "entries"} shown · newest first ·
          entries are write-once and cannot be edited or deleted
        </div>
      </div>
    </div>
  );
}
