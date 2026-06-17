import React, { useCallback, useEffect, useState } from "react";
import {
  X,
  Shield,
  Users,
  SlidersHorizontal,
  Building2,
  ScrollText,
  Loader2,
  AlertTriangle,
  UserPlus,
  Copy,
  Check,
  Trash2,
  Power,
  CreditCard,
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";

interface AdminConsoleModalProps {
  open: boolean;
  onClose: () => void;
}

type Tab = "team" | "risk" | "firm" | "audit";

interface Member {
  id: string;
  email: string;
  name: string;
  role: string;
  active: boolean;
  createdAt: string | null;
}

interface Invitation {
  id: string;
  email: string;
  name: string | null;
  role: string;
  status: string;
  createdAt: string | null;
  expiresAt: string | null;
}

interface Billing {
  plan: string;
  seats: number;
  seatsUsed: number;
  seatsAvailable: number;
  pendingInvites: number;
}

interface MembersPayload {
  firm: { id: string; name: string; plan: string; seats: number };
  members: Member[];
  invitations: Invitation[];
  roles: string[];
  billing: Billing;
  selfId: string;
}

interface LimitDef {
  key: string;
  label: string;
  unit: string;
  help: string;
}

interface LimitsPayload {
  limits: Record<string, number>;
  defs: LimitDef[];
  defaults: Record<string, number>;
  killSwitch: boolean;
  killReason: string | null;
}

interface AuditEntry {
  id: string;
  at: string;
  action: string;
  decision: string;
  summary: string;
  detail: Record<string, unknown>;
}

async function jsonOrThrow(res: Response) {
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: string } | null)?.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const TABS: { key: Tab; label: string; icon: React.ComponentType<{ className?: string; strokeWidth?: number }> }[] = [
  { key: "team", label: "Team", icon: Users },
  { key: "risk", label: "Risk", icon: SlidersHorizontal },
  { key: "firm", label: "Firm", icon: Building2 },
  { key: "audit", label: "Audit", icon: ScrollText },
];

export function AdminConsoleModal({ open, onClose }: AdminConsoleModalProps) {
  const { identity } = useAuth();
  const [tab, setTab] = useState<Tab>("team");

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-black border border-border flex flex-col max-h-[85vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-border shrink-0">
          <div className="flex flex-col gap-1">
            <span className="editorial-label text-[8.5px] text-muted-foreground flex items-center gap-1.5">
              <Shield className="w-3 h-3" strokeWidth={1.5} /> Firm Admin Console
            </span>
            <span className="font-serif text-xl leading-none">
              {identity?.firm.name || "Your firm"}
            </span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-white transition-colors">
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        <div className="flex items-center gap-1 px-6 pt-3 border-b border-border shrink-0">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 px-3 py-2 editorial-label text-[9px] border-b-2 -mb-px transition-colors ${
                  tab === t.key
                    ? "border-white text-white"
                    : "border-transparent text-muted-foreground hover:text-white"
                }`}
              >
                <Icon className="w-3 h-3" strokeWidth={1.5} /> {t.label}
              </button>
            );
          })}
        </div>

        <div className="overflow-y-auto px-6 py-5">
          {tab === "team" && <TeamTab />}
          {tab === "risk" && <RiskTab />}
          {tab === "firm" && <FirmTab />}
          {tab === "audit" && <AuditTab />}
        </div>
      </div>
    </div>
  );
}

function ErrorLine({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 text-amber-400">
      <AlertTriangle className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
      <span className="text-xs">{message}</span>
    </div>
  );
}

function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-muted-foreground py-6">
      <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} />
      <span className="text-xs font-serif">{label}</span>
    </div>
  );
}

// ------------------------------- Team tab ------------------------------------
function TeamTab() {
  const [data, setData] = useState<MembersPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState("trader");
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/admin/members");
      const d = (await jsonOrThrow(res)) as MembersPayload;
      setData(d);
    } catch (err: any) {
      setError(err?.message || "Couldn't load your team.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || inviting) return;
    setInviting(true);
    setInviteError(null);
    setInviteLink(null);
    setCopied(false);
    try {
      const res = await fetch("/api/admin/invitations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: inviteEmail.trim(), name: inviteName.trim(), role: inviteRole }),
      });
      const d = (await jsonOrThrow(res)) as { inviteToken: string; members: MembersPayload };
      setData(d.members);
      const url = `${window.location.origin}${window.location.pathname}?invite=${encodeURIComponent(d.inviteToken)}`;
      setInviteLink(url);
      setInviteEmail("");
      setInviteName("");
    } catch (err: any) {
      setInviteError(err?.message || "Couldn't send the invitation.");
    } finally {
      setInviting(false);
    }
  };

  const changeRole = async (userId: string, role: string) => {
    setBusyId(userId);
    setError(null);
    try {
      const res = await fetch(`/api/admin/users/${userId}/role`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      const d = (await jsonOrThrow(res)) as { members: MembersPayload };
      setData(d.members);
    } catch (err: any) {
      setError(err?.message || "Couldn't change the role.");
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = async (userId: string, active: boolean) => {
    setBusyId(userId);
    setError(null);
    try {
      const res = await fetch(`/api/admin/users/${userId}/active`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active }),
      });
      const d = (await jsonOrThrow(res)) as { members: MembersPayload };
      setData(d.members);
    } catch (err: any) {
      setError(err?.message || "Couldn't update the member.");
    } finally {
      setBusyId(null);
    }
  };

  const removeUser = async (userId: string) => {
    setBusyId(userId);
    setError(null);
    try {
      const res = await fetch(`/api/admin/users/${userId}`, { method: "DELETE" });
      const d = (await jsonOrThrow(res)) as MembersPayload;
      setData(d);
      setConfirmRemove(null);
    } catch (err: any) {
      setError(err?.message || "Couldn't remove the member.");
    } finally {
      setBusyId(null);
    }
  };

  const revokeInvite = async (inviteId: string) => {
    setBusyId(inviteId);
    setError(null);
    try {
      const res = await fetch(`/api/admin/invitations/${inviteId}`, { method: "DELETE" });
      const d = (await jsonOrThrow(res)) as MembersPayload;
      setData(d);
    } catch (err: any) {
      setError(err?.message || "Couldn't revoke the invitation.");
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <Spinner label="Loading your team…" />;
  if (error && !data) return <ErrorLine message={error} />;
  if (!data) return null;

  const roles = data.roles;

  return (
    <div className="flex flex-col gap-5">
      {/* Billing / seats summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-border border border-border">
        <Stat label="Plan" value={data.billing.plan} cap />
        <Stat label="Seats used" value={`${data.billing.seatsUsed} / ${data.billing.seats}`} />
        <Stat label="Available" value={String(data.billing.seatsAvailable)} />
        <Stat label="Pending" value={String(data.billing.pendingInvites)} />
      </div>

      {error && <ErrorLine message={error} />}

      {/* Invite form */}
      <form onSubmit={handleInvite} className="flex flex-col gap-3 border border-border px-4 py-4">
        <span className="editorial-label text-[8.5px] text-muted-foreground flex items-center gap-1.5">
          <UserPlus className="w-3 h-3" strokeWidth={1.5} /> Invite a teammate
        </span>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="email"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            placeholder="teammate@firm.com"
            disabled={inviting}
            className="flex-1 bg-transparent border border-border px-3 py-2 text-sm font-serif text-white placeholder:text-muted-foreground/60 focus:outline-none focus:border-white transition-colors"
          />
          <input
            type="text"
            value={inviteName}
            onChange={(e) => setInviteName(e.target.value)}
            placeholder="Name (optional)"
            disabled={inviting}
            className="flex-1 bg-transparent border border-border px-3 py-2 text-sm font-serif text-white placeholder:text-muted-foreground/60 focus:outline-none focus:border-white transition-colors"
          />
          <select
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value)}
            disabled={inviting}
            className="bg-black border border-border px-3 py-2 text-sm font-serif text-white focus:outline-none focus:border-white transition-colors capitalize"
          >
            {roles.map((r) => (
              <option key={r} value={r} className="bg-black capitalize">
                {r}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={!inviteEmail.trim() || inviting}
            className="flex items-center justify-center gap-2 bg-white text-black px-4 py-2 editorial-label text-[9px] disabled:opacity-40 hover:bg-white/90 transition-colors"
          >
            {inviting ? <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} /> : <UserPlus className="w-3 h-3" strokeWidth={2} />}
            Invite
          </button>
        </div>
        {inviteError && <ErrorLine message={inviteError} />}
        {inviteLink && (
          <div className="flex flex-col gap-2 border-t border-border pt-3">
            <span className="text-xs text-muted-foreground leading-relaxed">
              Share this one-time link with the invitee — it won't be shown again.
            </span>
            <div className="flex items-center gap-2">
              <code className="flex-1 truncate bg-white/5 border border-border px-2.5 py-1.5 text-[11px] text-white/90">
                {inviteLink}
              </code>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard?.writeText(inviteLink);
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 1500);
                }}
                className="shrink-0 flex items-center gap-1.5 border border-border px-3 py-1.5 editorial-label text-[9px] text-muted-foreground hover:text-white hover:border-white/40 transition-colors"
              >
                {copied ? <Check className="w-3 h-3 text-emerald-400" strokeWidth={2} /> : <Copy className="w-3 h-3" strokeWidth={2} />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        )}
      </form>

      {/* Members list */}
      <div className="flex flex-col gap-2">
        <span className="editorial-label text-[8.5px] text-muted-foreground">Members ({data.members.length})</span>
        {data.members.map((m) => {
          const isSelf = m.id === data.selfId;
          const busy = busyId === m.id;
          return (
            <div key={m.id} className="border border-border px-4 py-3 flex flex-col gap-2">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className="font-serif text-base leading-tight truncate flex items-center gap-2">
                    {m.name}
                    {isSelf && <span className="editorial-label text-[8px] text-muted-foreground">You</span>}
                    {!m.active && (
                      <span className="editorial-label text-[8px] text-red-400 border border-red-400/40 px-1.5 py-0.5">
                        Deactivated
                      </span>
                    )}
                  </span>
                  <span className="text-[11px] text-muted-foreground truncate">{m.email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={m.role}
                    disabled={busy || isSelf}
                    onChange={(e) => void changeRole(m.id, e.target.value)}
                    title={isSelf ? "You can't change your own role" : undefined}
                    className="bg-black border border-border px-2 py-1.5 text-xs font-serif text-white focus:outline-none focus:border-white transition-colors capitalize disabled:opacity-40"
                  >
                    {roles.map((r) => (
                      <option key={r} value={r} className="bg-black capitalize">
                        {r}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={() => void toggleActive(m.id, !m.active)}
                    disabled={busy || isSelf}
                    title={m.active ? "Deactivate" : "Reactivate"}
                    className="flex items-center gap-1 border border-border px-2 py-1.5 editorial-label text-[8.5px] text-muted-foreground hover:text-white hover:border-white/40 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  >
                    {busy ? <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} /> : <Power className="w-3 h-3" strokeWidth={1.5} />}
                    {m.active ? "Off" : "On"}
                  </button>
                  <button
                    onClick={() => setConfirmRemove(confirmRemove === m.id ? null : m.id)}
                    disabled={busy || isSelf}
                    title="Remove"
                    className="flex items-center text-muted-foreground hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                  </button>
                </div>
              </div>
              {confirmRemove === m.id && (
                <div className="flex items-center justify-between gap-3 border-t border-border pt-2.5">
                  <span className="text-xs text-muted-foreground">
                    Permanently remove <span className="text-white">{m.email}</span>?
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => void removeUser(m.id)}
                      disabled={busy}
                      className="flex items-center gap-1.5 bg-red-500/90 text-white px-3 py-1.5 editorial-label text-[9px] hover:bg-red-500 disabled:opacity-50 transition-colors"
                    >
                      {busy ? <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} /> : <Trash2 className="w-3 h-3" strokeWidth={2} />}
                      Remove
                    </button>
                    <button
                      onClick={() => setConfirmRemove(null)}
                      disabled={busy}
                      className="border border-border px-3 py-1.5 editorial-label text-[9px] text-muted-foreground hover:text-white hover:border-white/40 disabled:opacity-50 transition-colors"
                    >
                      Keep
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Pending invitations */}
      {data.invitations.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="editorial-label text-[8.5px] text-muted-foreground">
            Pending invitations ({data.invitations.length})
          </span>
          {data.invitations.map((inv) => (
            <div key={inv.id} className="border border-border border-dashed px-4 py-2.5 flex items-center justify-between gap-3">
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="font-serif text-sm truncate">{inv.email}</span>
                <span className="editorial-label text-[8px] text-muted-foreground capitalize">
                  {inv.role} · invited {fmtDate(inv.createdAt)} · expires {fmtDate(inv.expiresAt)}
                </span>
              </div>
              <button
                onClick={() => void revokeInvite(inv.id)}
                disabled={busyId === inv.id}
                className="shrink-0 flex items-center gap-1.5 border border-border px-3 py-1.5 editorial-label text-[8.5px] text-muted-foreground hover:text-red-400 hover:border-red-400/40 disabled:opacity-40 transition-colors"
              >
                {busyId === inv.id ? <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} /> : <X className="w-3 h-3" strokeWidth={2} />}
                Revoke
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, cap }: { label: string; value: string; cap?: boolean }) {
  return (
    <div className="bg-black px-3 py-2.5 flex flex-col gap-0.5">
      <span className="editorial-label text-[8px] text-muted-foreground">{label}</span>
      <span className={`font-serif text-base leading-none nums-tabular ${cap ? "capitalize" : ""}`}>{value}</span>
    </div>
  );
}

// ------------------------------- Risk tab ------------------------------------
function RiskTab() {
  const [data, setData] = useState<LimitsPayload | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [killBusy, setKillBusy] = useState(false);
  const [killReason, setKillReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/admin/limits");
      const d = (await jsonOrThrow(res)) as LimitsPayload;
      setData(d);
      const next: Record<string, string> = {};
      for (const def of d.defs) next[def.key] = String(d.limits[def.key] ?? d.defaults[def.key] ?? "");
      setDraft(next);
    } catch (err: any) {
      setError(err?.message || "Couldn't load risk limits.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const saveLimits = async () => {
    if (!data) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    const limits: Record<string, number> = {};
    for (const def of data.defs) {
      const raw = draft[def.key];
      const num = Number(raw);
      if (raw !== "" && Number.isFinite(num)) limits[def.key] = num;
    }
    try {
      const res = await fetch("/api/admin/limits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limits }),
      });
      const d = (await jsonOrThrow(res)) as LimitsPayload;
      setData(d);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (err: any) {
      setError(err?.message || "Couldn't save the limits.");
    } finally {
      setSaving(false);
    }
  };

  const toggleKill = async (on: boolean) => {
    setKillBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/admin/kill-switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ on, reason: on ? killReason.trim() || "Halted by admin" : null }),
      });
      const d = (await jsonOrThrow(res)) as { killSwitch: boolean; killReason: string | null };
      setData((prev) => (prev ? { ...prev, killSwitch: d.killSwitch, killReason: d.killReason } : prev));
      if (!on) setKillReason("");
    } catch (err: any) {
      setError(err?.message || "Couldn't update the kill switch.");
    } finally {
      setKillBusy(false);
    }
  };

  if (loading) return <Spinner label="Loading risk limits…" />;
  if (error && !data) return <ErrorLine message={error} />;
  if (!data) return null;

  return (
    <div className="flex flex-col gap-5">
      {error && <ErrorLine message={error} />}

      {/* Kill switch */}
      <div
        className={`flex flex-col gap-3 border px-4 py-4 ${
          data.killSwitch ? "border-red-400/50 bg-red-500/10" : "border-border"
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <span className="editorial-label text-[8.5px] text-muted-foreground flex items-center gap-1.5">
              <Power className="w-3 h-3" strokeWidth={1.5} /> Trading kill switch
            </span>
            <span className="text-xs text-muted-foreground leading-relaxed">
              {data.killSwitch
                ? `All trading halted firm-wide${data.killReason ? ` — ${data.killReason}` : ""}.`
                : "Engage to halt all paper trading and rebalancing firm-wide."}
            </span>
          </div>
          <button
            onClick={() => void toggleKill(!data.killSwitch)}
            disabled={killBusy}
            className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 editorial-label text-[9px] border transition-colors disabled:opacity-40 ${
              data.killSwitch
                ? "bg-white text-black border-white hover:bg-white/90"
                : "border-red-400/40 text-red-400 hover:bg-red-500/10"
            }`}
          >
            {killBusy ? <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} /> : <Power className="w-3 h-3" strokeWidth={2} />}
            {data.killSwitch ? "Release" : "Engage"}
          </button>
        </div>
        {!data.killSwitch && (
          <input
            type="text"
            value={killReason}
            onChange={(e) => setKillReason(e.target.value)}
            placeholder="Reason (optional)"
            className="bg-transparent border border-border px-3 py-2 text-xs font-serif text-white placeholder:text-muted-foreground/60 focus:outline-none focus:border-white transition-colors"
          />
        )}
      </div>

      {/* Limits editor */}
      <div className="flex flex-col gap-3">
        <span className="editorial-label text-[8.5px] text-muted-foreground">Firm risk limits</span>
        {data.defs.map((def) => (
          <label key={def.key} className="flex flex-col gap-1.5 border border-border px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="font-serif text-sm">{def.label}</span>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  step="any"
                  value={draft[def.key] ?? ""}
                  onChange={(e) => setDraft((p) => ({ ...p, [def.key]: e.target.value }))}
                  className="w-24 bg-transparent border border-border px-2 py-1.5 text-sm font-serif text-white text-right nums-tabular focus:outline-none focus:border-white transition-colors"
                />
                <span className="editorial-label text-[9px] text-muted-foreground w-3">{def.unit}</span>
              </div>
            </div>
            <span className="text-[11px] text-muted-foreground leading-relaxed">{def.help}</span>
          </label>
        ))}
        <button
          onClick={() => void saveLimits()}
          disabled={saving}
          className="self-start flex items-center gap-2 bg-white text-black px-4 py-2 editorial-label text-[9px] disabled:opacity-40 hover:bg-white/90 transition-colors"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} /> : saved ? <Check className="w-3 h-3" strokeWidth={2} /> : <SlidersHorizontal className="w-3 h-3" strokeWidth={2} />}
          {saved ? "Saved" : "Save limits"}
        </button>
      </div>
    </div>
  );
}

// ------------------------------- Firm tab ------------------------------------
function FirmTab() {
  const { identity } = useAuth();
  const [name, setName] = useState(identity?.firm.name || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [billing, setBilling] = useState<Billing | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/admin/members");
        const d = (await jsonOrThrow(res)) as MembersPayload;
        setBilling(d.billing);
        setName((cur) => cur || d.firm.name);
      } catch {
        /* billing view is best-effort */
      }
    })();
  }, []);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || saving) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const res = await fetch("/api/admin/firm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      await jsonOrThrow(res);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (err: any) {
      setError(err?.message || "Couldn't update the firm.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <form onSubmit={save} className="flex flex-col gap-3 border border-border px-4 py-4">
        <span className="editorial-label text-[8.5px] text-muted-foreground flex items-center gap-1.5">
          <Building2 className="w-3 h-3" strokeWidth={1.5} /> Firm profile
        </span>
        <label className="flex flex-col gap-1.5">
          <span className="editorial-label text-[9px] text-muted-foreground">Firm name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="bg-transparent border border-border px-3 py-2.5 text-sm font-serif text-white focus:outline-none focus:border-white transition-colors"
          />
        </label>
        {error && <ErrorLine message={error} />}
        <button
          type="submit"
          disabled={!name.trim() || saving}
          className="self-start flex items-center gap-2 bg-white text-black px-4 py-2 editorial-label text-[9px] disabled:opacity-40 hover:bg-white/90 transition-colors"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} /> : saved ? <Check className="w-3 h-3" strokeWidth={2} /> : <Building2 className="w-3 h-3" strokeWidth={2} />}
          {saved ? "Saved" : "Save profile"}
        </button>
      </form>

      <div className="flex flex-col gap-3 border border-border px-4 py-4">
        <span className="editorial-label text-[8.5px] text-muted-foreground flex items-center gap-1.5">
          <CreditCard className="w-3 h-3" strokeWidth={1.5} /> Billing (read-only)
        </span>
        {billing ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-border border border-border">
            <Stat label="Plan" value={billing.plan} cap />
            <Stat label="Seats" value={String(billing.seats)} />
            <Stat label="Used" value={String(billing.seatsUsed)} />
            <Stat label="Available" value={String(billing.seatsAvailable)} />
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">Billing details unavailable.</span>
        )}
        <span className="text-[11px] text-muted-foreground leading-relaxed">
          Plan changes and payment are managed by your account team — this view is informational only.
        </span>
      </div>
    </div>
  );
}

// ------------------------------- Audit tab -----------------------------------
function AuditTab() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/admin/audit?limit=100");
        const d = (await jsonOrThrow(res)) as { entries: AuditEntry[] };
        setEntries(d.entries);
      } catch (err: any) {
        setError(err?.message || "Couldn't load the audit trail.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <Spinner label="Loading audit trail…" />;
  if (error) return <ErrorLine message={error} />;
  if (!entries || entries.length === 0) {
    return <p className="text-sm text-muted-foreground py-6">No audit entries yet.</p>;
  }

  return (
    <div className="flex flex-col gap-px bg-border border border-border">
      {entries.map((e) => (
        <div key={e.id} className="bg-black px-4 py-2.5 flex items-start justify-between gap-3">
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="text-xs text-white leading-snug">{e.summary}</span>
            <span className="editorial-label text-[8px] text-muted-foreground">{e.action}</span>
          </div>
          <span className="editorial-label text-[8px] text-muted-foreground shrink-0 nums-tabular">{fmtTime(e.at)}</span>
        </div>
      ))}
    </div>
  );
}
