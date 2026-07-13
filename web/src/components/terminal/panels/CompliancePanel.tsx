// @ts-nocheck
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Plus,
  Trash2,
  AlertTriangle,
  Power,
  CheckCircle2,
  XCircle,
} from "lucide-react";

interface LimitDef {
  key: string;
  label: string;
  unit: string;
  help: string;
}

interface CheckRow {
  key: string;
  label: string;
  unit: string;
  value: number;
  limit: number;
  status: "ok" | "warn" | "breach";
  utilization: number;
  detail: string;
}

interface Metrics {
  gross: number;
  net: number;
  leverage: number;
  maxPositionPct: number;
  maxPositionName?: string | null;
  concentrationPct: number;
  topNames?: string[];
  names: number;
}

interface StrategyRow {
  id?: string;
  name?: string;
  stage?: string;
}

interface AuditRow {
  id?: string;
  at?: string;
  action?: string;
  strategyName?: string | null;
  strategyId?: string | null;
  decision?: string;
  summary?: string | null;
}

interface CheckResult {
  strategyId?: string;
  strategyName?: string;
  stage?: string;
  ok: boolean;
  blocked: boolean;
  reason?: string | null;
  checks: CheckRow[];
  metrics: Metrics;
  restricted: string[];
  watch: string[];
  violations: string[];
  warnings: string[];
  killSwitch: boolean;
  killReason?: string | null;
  killSource?: "none" | "tenant" | "global" | "environment" | "missing_control_store";
  killVersion?: number;
}

interface ComplianceData {
  limits: Record<string, number>;
  limitDefs: LimitDef[];
  restricted: string[];
  watch: string[];
  policyConfigured?: boolean;
  limitsEnforced?: boolean;
  policyVersion?: number;
  killSwitch: boolean;
  killReason?: string | null;
  strategyKills?: Record<string, string>;
  strategies: StrategyRow[];
  audit: AuditRow[];
  check?: CheckResult | null;
}

interface CompliancePanelProps {
  data: ComplianceData;
}

const STATUS_COLOR: Record<string, string> = {
  ok: "text-emerald-400",
  warn: "text-amber-400",
  breach: "text-red-400",
};

function fmtNum(v: number, unit: string): string {
  if (unit === "x") return `${v.toFixed(2)}x`;
  if (unit === "%") return `${v.toFixed(1)}%`;
  return v.toLocaleString();
}

function fmtTime(at?: string): string {
  if (!at) return "";
  const t = new Date(at).getTime();
  if (Number.isNaN(t)) return "";
  const secs = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function CompliancePanel({ data }: CompliancePanelProps) {
  const [state, setState] = useState<ComplianceData>(data);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newRestricted, setNewRestricted] = useState("");
  const [newWatch, setNewWatch] = useState("");
  const [limitDraft, setLimitDraft] = useState<Record<string, string>>({});
  const [selStrategy, setSelStrategy] = useState<string>("");

  const limitDefs = state?.limitDefs ?? [];

  useEffect(() => {
    setState(data);
  }, [data]);

  useEffect(() => {
    // Seed the editable limit drafts from server values.
    const d: Record<string, string> = {};
    for (const def of state?.limitDefs ?? []) {
      const v = state?.limits?.[def.key];
      if (v != null) d[def.key] = String(v);
    }
    setLimitDraft(d);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.limits]);

  const apply = useCallback(
    async (path: string, init?: RequestInit) => {
      setBusy(true);
      setError(null);
      try {
        const res = await fetch(`/api/compliance${path}`, init);
        const json = await res.json().catch(() => ({}));
        if (!res.ok) {
          setError(typeof json.detail === "string" ? json.detail : "Request failed.");
          if (res.status === 409) {
            const latest = await fetch("/api/compliance");
            if (latest.ok) setState(await latest.json());
          }
          return false;
        }
        setState(json);
        return true;
      } catch {
        setError("Network error.");
        return false;
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/compliance");
      if (!res.ok) return;
      setState(await res.json());
    } catch {
      /* keep last good state */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addRestricted = async (e: React.FormEvent) => {
    e.preventDefault();
    const sym = newRestricted.trim().toUpperCase();
    if (!sym) return;
    if (await apply("/restricted", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: sym, expect_version: state.policyVersion ?? 0 }),
    })) setNewRestricted("");
  };

  const addWatch = async (e: React.FormEvent) => {
    e.preventDefault();
    const sym = newWatch.trim().toUpperCase();
    if (!sym) return;
    if (await apply("/watch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: sym, expect_version: state.policyVersion ?? 0 }),
    })) setNewWatch("");
  };

  const removeFrom = (list: "restricted" | "watch", sym: string) =>
    apply(`/${list}/${encodeURIComponent(sym)}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expect_version: state.policyVersion ?? 0 }),
    });

  const saveLimits = async () => {
    const limits: Record<string, number> = {};
    for (const def of limitDefs) {
      const raw = limitDraft[def.key];
      const v = parseFloat(raw);
      if (Number.isFinite(v) && v > 0) limits[def.key] = v;
    }
    await apply("/limits", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limits, expect_version: state.policyVersion ?? 0 }),
    });
  };

  const toggleKill = () =>
    apply("/kill-switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        on: !state.killSwitch,
        reason: state.killSwitch ? null : "Engaged from compliance panel",
        expect_version: state.killVersion ?? 0,
      }),
    });

  const runCheck = async () => {
    if (!selStrategy) return;
    await apply("/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy_id: selStrategy }),
    });
  };

  const check = state?.check ?? null;
  const tenantCanToggleKill = state.killSource === "none" || state.killSource === "tenant";
  const limitsDirty = useMemo(() => {
    for (const def of limitDefs) {
      const cur = state?.limits?.[def.key];
      if (cur == null) continue;
      if (String(cur) !== (limitDraft[def.key] ?? "")) return true;
    }
    return false;
  }, [limitDefs, limitDraft, state?.limits]);

  return (
    <div className="w-full h-full flex flex-col gap-3 text-white overflow-y-auto scrollbar-none">
      {/* Kill switch */}
      <div
        className={`shrink-0 flex items-center justify-between gap-3 border px-3 py-2 ${
          state.killSwitch ? "border-red-500/70 bg-red-500/10" : "border-border"
        }`}
      >
        <div className="flex items-center gap-2 min-w-0">
          {state.killSwitch ? (
            <ShieldAlert className="w-4 h-4 text-red-400 shrink-0" strokeWidth={1.5} />
          ) : (
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" strokeWidth={1.5} />
          )}
          <div className="min-w-0">
            <div className="editorial-label text-[9px]">
              Kill switch · {state.killSwitch ? "ENGAGED" : "armed"}
            </div>
            <div className="text-[10px] text-muted-foreground truncate">
              {state.killSwitch
                ? state.killReason || "All trading halted."
                : "Trading permitted, subject to limits."}
            </div>
          </div>
        </div>
        <button
          onClick={toggleKill}
          disabled={busy || !tenantCanToggleKill}
          title={
            tenantCanToggleKill
              ? undefined
              : "This site-wide halt can only be released by an operator."
          }
          className={`flex items-center gap-1.5 border px-2.5 py-1 editorial-label text-[9px] disabled:opacity-40 transition-colors ${
            state.killSwitch
              ? "border-border hover:bg-white/10"
              : "border-red-500/70 text-red-300 hover:bg-red-500/20"
          }`}
        >
          <Power className="w-3 h-3" strokeWidth={2} />
          {!tenantCanToggleKill ? "Site halt" : state.killSwitch ? "Release" : "Halt all"}
        </button>
      </div>

      {error && (
        <div className="shrink-0 flex items-center gap-1.5 text-[10px] text-amber-400">
          <AlertTriangle className="w-3 h-3" strokeWidth={1.5} />
          {error}
        </div>
      )}

      {/* Firm limits */}
      <section className="shrink-0">
        <div className="editorial-label text-[8.5px] text-muted-foreground mb-1.5">
          Firm limits · {state.limitsEnforced ? `active · policy v${state.policyVersion}` : "reference defaults"}
        </div>
        <p className="mb-2 text-[9px] leading-tight text-muted-foreground/70">
          Applied to strategy promotion and paper books. Direct orders use order-level
          notional and quantity caps.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {limitDefs.map((def) => (
            <label key={def.key} className="flex flex-col gap-1" title={def.help}>
              <span className="text-[9px] text-muted-foreground">{def.label}</span>
              <div className="relative flex items-center">
                <input
                  value={limitDraft[def.key] ?? ""}
                  onChange={(e) =>
                    setLimitDraft((d) => ({ ...d, [def.key]: e.target.value }))
                  }
                  inputMode="decimal"
                  className="w-full bg-transparent border border-border pl-2 pr-7 py-1 text-sm nums-tabular focus:outline-none focus:border-white transition-colors"
                />
                <span className="absolute right-2 text-[9px] text-muted-foreground">
                  {def.unit}
                </span>
              </div>
            </label>
          ))}
        </div>
        {limitsDirty && (
          <button
            onClick={saveLimits}
            disabled={busy}
            className="mt-2 w-full border border-border bg-white text-black py-1.5 editorial-label text-[9px] hover:bg-gray-200 disabled:opacity-40 transition-colors"
          >
            Save limits
          </button>
        )}
      </section>

      {/* Restricted + watch lists */}
      <section className="shrink-0 grid grid-cols-2 gap-3">
        <div>
          <div className="editorial-label text-[8.5px] text-red-300/80 mb-1.5">
            Restricted · {state.restricted?.length ?? 0}
          </div>
          <form onSubmit={addRestricted} className="flex gap-1 mb-1.5">
            <input
              value={newRestricted}
              onChange={(e) => setNewRestricted(e.target.value.toUpperCase())}
              placeholder="TICKER"
              className="flex-1 min-w-0 bg-transparent border border-border px-2 py-1 text-xs font-serif uppercase focus:outline-none focus:border-white transition-colors"
            />
            <button
              type="submit"
              disabled={busy}
              className="border border-border px-2 hover:bg-white/10 disabled:opacity-40 transition-colors"
              aria-label="Add restricted name"
            >
              <Plus className="w-3 h-3" strokeWidth={2} />
            </button>
          </form>
          <ul className="flex flex-col">
            {(state.restricted ?? []).map((s) => (
              <li
                key={s}
                className="flex items-center justify-between py-1 border-b border-border/60 group/it"
              >
                <span className="font-serif text-sm">{s}</span>
                <button
                  onClick={() => removeFrom("restricted", s)}
                  className="text-muted-foreground hover:text-red-400 opacity-0 group-hover/it:opacity-100 transition-colors"
                  aria-label={`Remove ${s}`}
                >
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                </button>
              </li>
            ))}
            {(state.restricted ?? []).length === 0 && (
              <li className="text-[10px] text-muted-foreground italic py-1">None</li>
            )}
          </ul>
        </div>
        <div>
          <div className="editorial-label text-[8.5px] text-amber-300/80 mb-1.5">
            Watch · {state.watch?.length ?? 0}
          </div>
          <form onSubmit={addWatch} className="flex gap-1 mb-1.5">
            <input
              value={newWatch}
              onChange={(e) => setNewWatch(e.target.value.toUpperCase())}
              placeholder="TICKER"
              className="flex-1 min-w-0 bg-transparent border border-border px-2 py-1 text-xs font-serif uppercase focus:outline-none focus:border-white transition-colors"
            />
            <button
              type="submit"
              disabled={busy}
              className="border border-border px-2 hover:bg-white/10 disabled:opacity-40 transition-colors"
              aria-label="Add watch name"
            >
              <Plus className="w-3 h-3" strokeWidth={2} />
            </button>
          </form>
          <ul className="flex flex-col">
            {(state.watch ?? []).map((s) => (
              <li
                key={s}
                className="flex items-center justify-between py-1 border-b border-border/60 group/it"
              >
                <span className="font-serif text-sm">{s}</span>
                <button
                  onClick={() => removeFrom("watch", s)}
                  className="text-muted-foreground hover:text-red-400 opacity-0 group-hover/it:opacity-100 transition-colors"
                  aria-label={`Remove ${s}`}
                >
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                </button>
              </li>
            ))}
            {(state.watch ?? []).length === 0 && (
              <li className="text-[10px] text-muted-foreground italic py-1">None</li>
            )}
          </ul>
        </div>
      </section>

      {/* Pre-trade check */}
      <section className="shrink-0">
        <div className="editorial-label text-[8.5px] text-muted-foreground mb-1.5">
          Pre-trade check
        </div>
        <div className="flex gap-1.5">
          <select
            value={selStrategy}
            onChange={(e) => setSelStrategy(e.target.value)}
            className="flex-1 min-w-0 bg-black border border-border px-2 py-1.5 text-xs font-serif focus:outline-none focus:border-white transition-colors"
          >
            <option value="">Select a strategy…</option>
            {(state.strategies ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · {s.stage}
              </option>
            ))}
          </select>
          <button
            onClick={runCheck}
            disabled={busy || !selStrategy}
            className="border border-border bg-white text-black px-3 editorial-label text-[9px] hover:bg-gray-200 disabled:opacity-40 transition-colors"
          >
            Check
          </button>
        </div>

        {check && (
          <div className="mt-2 border border-border p-2.5">
            <div className="flex items-center gap-2 mb-2">
              {check.ok ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
              ) : (
                <XCircle className="w-4 h-4 text-red-400" strokeWidth={1.5} />
              )}
              <span className="font-serif text-sm">
                {check.strategyName}
              </span>
              <span
                className={`editorial-label text-[9px] ${
                  check.ok ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {check.ok ? "Allowed" : "Blocked"}
              </span>
            </div>
            {!check.ok && check.reason && (
              <p className="text-[10px] text-red-300 leading-snug mb-2">{check.reason}</p>
            )}
            <ul className="flex flex-col gap-1">
              {check.checks.map((c) => (
                <li
                  key={c.key}
                  className="flex items-center justify-between text-[10px]"
                >
                  <span className="text-muted-foreground truncate">{c.detail}</span>
                  <span className={`nums-tabular ${STATUS_COLOR[c.status]}`}>
                    {fmtNum(c.value, c.unit)} / {fmtNum(c.limit, c.unit)}
                  </span>
                </li>
              ))}
            </ul>
            {check.warnings.length > 0 && (
              <ul className="mt-1.5 flex flex-col gap-0.5">
                {check.warnings.map((w, i) => (
                  <li
                    key={i}
                    className="text-[10px] text-amber-300 leading-snug border-l border-amber-400/60 pl-2"
                  >
                    {w}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* Audit trail */}
      <section className="flex-1 min-h-0">
        <div className="editorial-label text-[8.5px] text-muted-foreground mb-1.5">
          Audit trail · {state.audit?.length ?? 0}
        </div>
        {(state.audit ?? []).length === 0 ? (
          <p className="font-serif text-sm text-muted-foreground italic py-1">
            No gate decisions recorded yet.
          </p>
        ) : (
          <ul className="flex flex-col">
            {(state.audit ?? []).map((a, i) => {
              const blocked = a.decision === "blocked";
              const warn = a.decision === "warn";
              return (
                <li
                  key={a.id ?? i}
                  className="flex items-start justify-between gap-2 py-1 border-b border-border/60"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      {blocked ? (
                        <XCircle className="w-3 h-3 text-red-400 shrink-0" strokeWidth={1.5} />
                      ) : warn ? (
                        <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" strokeWidth={1.5} />
                      ) : (
                        <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" strokeWidth={1.5} />
                      )}
                      <span className="text-[11px] truncate">
                        {a.action}
                        {a.strategyName ? ` · ${a.strategyName}` : ""}
                      </span>
                    </div>
                    {(blocked || warn) && a.summary && (
                      <p
                        className={`text-[9.5px] leading-snug pl-4.5 ${
                          blocked ? "text-red-300/90" : "text-amber-300/90"
                        }`}
                      >
                        {a.summary}
                      </p>
                    )}
                  </div>
                  <span className="text-[9px] text-muted-foreground shrink-0 nums-tabular">
                    {fmtTime(a.at)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
