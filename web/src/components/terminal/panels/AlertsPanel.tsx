// @ts-nocheck
import React, { useCallback, useEffect, useState } from "react";
import { BellRing, Plus, Trash2, AlertTriangle } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

interface Metric {
  id: string;
  label: string;
  unit: string;
  help: string;
}

interface Rule {
  id: string;
  symbol: string;
  metric: string;
  metricLabel: string;
  threshold: number;
  createdAt?: string;
}

interface AlertEvent {
  id: string;
  symbol: string;
  metricLabel: string;
  message: string;
  at?: string;
}

interface AlertsData {
  symbol?: string | null;
  metrics?: Metric[];
}

interface AlertsPanelProps {
  data: AlertsData;
  sessionId?: string;
}

const FALLBACK_METRICS: Metric[] = [
  { id: "block_size", label: "Block print size", unit: "shares", help: "" },
  { id: "dark_pool_pct", label: "Dark pool share", unit: "%", help: "" },
  { id: "buy_imbalance", label: "Buy imbalance", unit: "%", help: "" },
];

function defaultThreshold(metric: string): string {
  if (metric === "block_size") return "50000";
  if (metric === "dark_pool_pct") return "45";
  if (metric === "buy_imbalance") return "65";
  return "";
}

export function AlertsPanel({ data, sessionId }: AlertsPanelProps) {
  const { can } = useAuth();
  const canManage = can("alert.manage");
  const metrics = data?.metrics?.length ? data.metrics : FALLBACK_METRICS;

  const [rules, setRules] = useState<Rule[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [symbol, setSymbol] = useState((data?.symbol || "").toUpperCase());
  const [metric, setMetric] = useState(metrics[0]?.id ?? "block_size");
  const [threshold, setThreshold] = useState(defaultThreshold(metrics[0]?.id ?? "block_size"));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await fetch(`/api/alerts?sessionId=${encodeURIComponent(sessionId)}`);
      if (!res.ok) return;
      const json = await res.json();
      setRules(json.rules ?? []);
      setEvents(json.events ?? []);
    } catch {
      /* transient — keep last good state */
    }
  }, [sessionId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const activeMetric = metrics.find((m) => m.id === metric) ?? metrics[0];

  const handleMetricChange = (id: string) => {
    setMetric(id);
    setThreshold(defaultThreshold(id));
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!sessionId) {
      setError("No active session yet.");
      return;
    }
    const sym = symbol.trim().toUpperCase();
    const thr = parseFloat(threshold);
    if (!sym) {
      setError("Enter a ticker.");
      return;
    }
    if (!Number.isFinite(thr) || thr <= 0) {
      setError("Enter a positive threshold.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId, symbol: sym, metric, threshold: thr }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(json.detail || "Could not add rule.");
        return;
      }
      setRules(json.rules ?? []);
      setEvents(json.events ?? []);
    } catch {
      setError("Network error.");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (ruleId: string) => {
    if (!sessionId) return;
    try {
      const res = await fetch(
        `/api/alerts/${ruleId}?sessionId=${encodeURIComponent(sessionId)}`,
        { method: "DELETE" },
      );
      const json = await res.json().catch(() => ({}));
      if (res.ok) {
        setRules(json.rules ?? []);
        setEvents(json.events ?? []);
      }
    } catch {
      /* ignore */
    }
  };

  const unitFor = (m: string) => metrics.find((x) => x.id === m)?.unit ?? "";

  return (
    <div className="w-full h-full flex flex-col gap-3 text-white overflow-hidden">
      {/* Rule builder */}
      <form onSubmit={handleAdd} className="shrink-0 flex flex-col gap-2">
        <div className="grid grid-cols-[1fr_1.4fr_1fr] gap-2">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="TICKER"
            className="bg-transparent border border-border px-2 py-1.5 text-sm font-serif uppercase tracking-wide focus:outline-none focus:border-white transition-colors"
          />
          <select
            value={metric}
            onChange={(e) => handleMetricChange(e.target.value)}
            className="bg-black border border-border px-2 py-1.5 text-xs font-serif focus:outline-none focus:border-white transition-colors"
          >
            {metrics.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
          <div className="relative flex items-center">
            <input
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              inputMode="decimal"
              placeholder="0"
              className="w-full bg-transparent border border-border pl-2 pr-7 py-1.5 text-sm nums-tabular focus:outline-none focus:border-white transition-colors"
            />
            <span className="absolute right-2 text-[9px] text-muted-foreground uppercase">
              {unitFor(metric)}
            </span>
          </div>
        </div>
        {activeMetric?.help && (
          <p className="editorial-label text-[8.5px] text-muted-foreground leading-snug normal-case tracking-normal">
            {activeMetric.help}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !canManage}
          title={canManage ? undefined : "Managing alerts requires the analyst role or higher"}
          className="flex items-center justify-center gap-2 border border-border bg-white text-black py-1.5 editorial-label text-[9px] hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Plus className="w-3 h-3" strokeWidth={2} />
          Add Alert Rule
        </button>
        {error && (
          <div className="flex items-center gap-1.5 text-[10px] text-amber-400">
            <AlertTriangle className="w-3 h-3" strokeWidth={1.5} />
            {error}
          </div>
        )}
      </form>

      {/* Active rules */}
      <div className="flex-1 min-h-0 overflow-y-auto scrollbar-none border-t border-border pt-2">
        <div className="editorial-label text-[8.5px] text-muted-foreground mb-1.5">
          Active Rules · {rules.length}
        </div>
        {rules.length === 0 ? (
          <p className="font-serif text-sm text-muted-foreground italic py-2">
            No rules yet. Add one above to start watching the tape.
          </p>
        ) : (
          <ul className="flex flex-col">
            {rules.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between gap-2 py-1.5 border-b border-border/60 group/rule"
              >
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="font-serif text-sm shrink-0">{r.symbol}</span>
                  <span className="text-[10px] text-muted-foreground truncate">
                    {r.metricLabel} ≥{" "}
                    <span className="nums-tabular text-gray-200">
                      {r.threshold.toLocaleString()}
                    </span>
                    {unitFor(r.metric) === "%" ? "%" : ""}
                  </span>
                </div>
                {canManage && (
                  <button
                    onClick={() => handleDelete(r.id)}
                    className="text-muted-foreground hover:text-red-400 transition-colors shrink-0 opacity-0 group-hover/rule:opacity-100"
                    aria-label="Delete rule"
                  >
                    <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {events.length > 0 && (
          <>
            <div className="editorial-label text-[8.5px] text-muted-foreground mt-3 mb-1.5 flex items-center gap-1.5">
              <BellRing className="w-3 h-3" strokeWidth={1.5} />
              Triggered · {events.length}
            </div>
            <ul className="flex flex-col gap-1">
              {events.slice(0, 8).map((ev) => (
                <li key={ev.id} className="text-[10px] text-gray-300 leading-snug border-l border-amber-400/60 pl-2 py-0.5">
                  {ev.message}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
