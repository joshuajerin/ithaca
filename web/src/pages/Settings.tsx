import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api";
import { MCP_BASE } from "../config";

const SCOPES: { id: string; label: string; desc: string }[] = [
  { id: "data:read",       label: "Read market data",   desc: "Access live and historical price feeds" },
  { id: "strategy:author", label: "Author strategies",  desc: "Create and edit strategy definitions" },
  { id: "runs:write",      label: "Create runs",        desc: "Trigger backtests and live sessions" },
  { id: "runs:cancel",     label: "Cancel runs",        desc: "Halt in-flight sessions" },
  { id: "approvals:read",  label: "Read approvals",     desc: "Inspect approval queues" },
  { id: "artifacts:read",  label: "Read artifacts",     desc: "Download backtest artifacts" },
  { id: "deploy:backtest", label: "Run backtests",      desc: "Execute backtest pipelines" },
];

type KeyRow = { key_id: string; scopes: string[]; created_at: string; revoked: boolean };

function fmtDate(v: string | number): string {
  const d = new Date(typeof v === "number" ? v * 1000 : v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleDateString();
}

function SearchIcon() {
  return (
    <svg className="searchbar-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <circle cx="6.5" cy="6.5" r="4" /><line x1="10" y1="10" x2="14" y2="14" />
    </svg>
  );
}

export function Settings() {
  const { user, manageAccount, signOut } = useAuth();

  const [query, setQuery] = useState("");
  const [keys, setKeys] = useState<KeyRow[]>([]);
  const [loadingKeys, setLoadingKeys] = useState(true);
  const [keysError, setKeysError] = useState<string | null>(null);
  const [selectedScopes, setSelectedScopes] = useState<string[]>(() => SCOPES.map((s) => s.id));
  const [minting, setMinting] = useState(false);
  const [freshKey, setFreshKey] = useState<{ api_key: string; key_id: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [copiedSetup, setCopiedSetup] = useState<string | null>(null);

  async function loadKeys() {
    setLoadingKeys(true);
    setKeysError(null);
    try {
      setKeys(await api.listKeys());
    } catch (e) {
      if (isUnauthorized(e)) {
        setKeys([]);
      } else {
        setKeysError("Could not load keys.");
      }
    } finally {
      setLoadingKeys(false);
    }
  }

  useEffect(() => { void loadKeys(); }, []);

  function toggleScope(id: string) {
    setSelectedScopes((cur) =>
      cur.includes(id) ? cur.filter((s) => s !== id) : [...cur, id],
    );
  }

  async function generateKey() {
    setMinting(true);
    setKeysError(null);
    setFreshKey(null);
    try {
      const res = await api.mintKey(selectedScopes);
      setFreshKey({ api_key: res.api_key, key_id: res.key_id });
      await loadKeys();
    } catch (e) {
      setKeysError(settingsError(e));
    } finally {
      setMinting(false);
    }
  }

  async function revoke(keyId: string) {
    setKeysError(null);
    try {
      await api.revokeKey(keyId);
      if (freshKey?.key_id === keyId) setFreshKey(null);
      await loadKeys();
    } catch (e) {
      setKeysError(settingsError(e));
    }
  }

  function copyFresh() {
    if (!freshKey) return;
    navigator.clipboard?.writeText(freshKey.api_key).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  }

  function copySetup(id: string, value: string) {
    navigator.clipboard?.writeText(value).then(() => {
      setCopiedSetup(id);
      window.setTimeout(() => setCopiedSetup(null), 1500);
    });
  }

  if (!user) return null;
  const initials = user.name.split(" ").map((s: string) => s[0]).slice(0, 2).join("").toUpperCase();
  const activeKeys = keys.filter((k) => !k.revoked);

  return (
    <div className="page" style={{ padding: 0, overflow: "auto" }}>
      {/* Topbar */}
      <div className="topbar">
        <div className="topbar-left">
          <div className="topbar-title">Settings</div>
        </div>
        <div className="searchbar-wrap">
          <SearchIcon />
          <input
            className="searchbar"
            type="search"
            placeholder="Search settings..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="topbar-right" />
      </div>

      <div style={{ padding: "4px 24px 40px", maxWidth: 820 }}>

        {/* ── Profile ──────────────────────────────────────────────────── */}
        <div className="settings-section">
          <div className="settings-section-label">Profile</div>
          <div className="fcard">
            <div className="settings-profile-row">
              <div className="settings-avatar">
                {user.avatarUrl ? <img src={user.avatarUrl} alt="" /> : <span>{initials}</span>}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 650, fontSize: 15, marginBottom: 3, color: "var(--fg)" }}>
                  {user.name}
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
                  {user.email}
                </div>
              </div>
              <button className="settings-btn" onClick={manageAccount}>
                Manage account
              </button>
            </div>
          </div>
        </div>

        {/* ── Connect an agent ─────────────────────────────────────────── */}
        <div className="settings-section" id="connect-agent">
          <div className="settings-section-label">Connect an agent</div>
          <div className="fcard" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <p style={{ margin: 0, color: "var(--muted)", fontSize: 12 }}>
              Setup opens app.tradeithaca.com first, then Clerk’s approve/deny screen.
              Your agent can refresh the connection for at least 30 days unless you revoke
              access or clear its local credentials.
            </p>
            {[
              {
                id: "codex",
                label: "Codex",
                command: "curl -fsSL https://app.tradeithaca.com/install.py | python3 - --client codex --login",
                detail: "Preserves an existing valid connection, then signs in.",
              },
              {
                id: "claude",
                label: "Claude Code",
                command: "curl -fsSL https://app.tradeithaca.com/install.py | python3 - --client claude-code --login",
                detail: "Preserves an existing valid connection, then signs in.",
              },
              {
                id: "generic",
                label: "Any MCP client",
                command: JSON.stringify({ mcpServers: { ithaca: { type: "http", url: MCP_BASE } } }, null, 2),
                detail: "Works with any agent that supports standard remote MCP and OAuth.",
              },
            ].map((client) => (
              <div key={client.id} style={{ borderTop: "1px solid var(--border-soft)", paddingTop: 12 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                  <strong style={{ fontSize: 13 }}>{client.label}</strong>
                  <button className="settings-btn" onClick={() => copySetup(client.id, client.command)}>
                    {copiedSetup === client.id ? "Copied" : "Copy"}
                  </button>
                </div>
                <code style={{ display: "block", marginTop: 8, whiteSpace: "pre-wrap", fontSize: 11, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>{client.command}</code>
                <div style={{ marginTop: 6, fontSize: 11, color: "var(--muted-dim)" }}>
                  {client.detail}
                </div>
              </div>
            ))}
            <a href="https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization" target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--accent)" }}>
              Troubleshooting OAuth discovery or login ↗
            </a>
          </div>
        </div>

        {/* ── Automation & compatibility keys ───────────────────────────── */}
        <div className="settings-section">
          <div className="settings-section-label">Automation &amp; compatibility keys</div>
          <div className="fcard" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <p style={{ margin: 0, fontSize: 12, color: "var(--muted)" }}>
              Use scoped keys only for CI or agents that cannot complete standard MCP OAuth.
            </p>

            {/* Scope picker */}
            <div>
              <div className="settings-field-label">Permissions</div>
              <div className="settings-scope-grid">
                {SCOPES.map((s) => (
                  <label key={s.id} className="settings-scope-item">
                    <input
                      type="checkbox"
                      checked={selectedScopes.includes(s.id)}
                      onChange={() => toggleScope(s.id)}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 500 }}>{s.label}</div>
                      <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 1 }}>{s.desc}</div>
                    </div>
                    <code style={{ fontSize: 10, color: "var(--muted-dim)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
                      {s.id}
                    </code>
                  </label>
                ))}
              </div>
              <div style={{ marginTop: 14 }}>
                <button
                  className="settings-btn primary"
                  onClick={generateKey}
                  disabled={minting || selectedScopes.length === 0}
                >
                  {minting ? "Generating…" : "Generate key"}
                </button>
              </div>
            </div>

            {/* Newly minted key */}
            {freshKey && (
              <div className="settings-fresh-key">
                <div className="settings-field-label" style={{ color: "#3d6b1c" }}>
                  New key — copy now, shown only once
                </div>
                <code style={{
                  display: "block",
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  wordBreak: "break-all",
                  color: "var(--fg)",
                  background: "#ffffff",
                  padding: "10px 12px",
                  borderRadius: 8,
                  marginBottom: 10,
                  border: "1px solid #c5dda8",
                }}>
                  {freshKey.api_key}
                </code>
                <button className="settings-btn primary" onClick={copyFresh}>
                  {copied ? "Copied!" : "Copy key"}
                </button>
              </div>
            )}

            {keysError && (
              <div style={{ color: "var(--neg)", fontSize: 12, padding: "8px 12px", background: "#fff0f0", borderRadius: 8, border: "1px solid #f0b3b3" }}>
                {keysError}
              </div>
            )}

            {/* Active keys list */}
            <div style={{ paddingTop: 16, borderTop: "1px solid var(--border-soft)" }}>
              <div className="settings-field-label">
                Active keys ({loadingKeys ? "…" : activeKeys.length})
              </div>
              {loadingKeys ? (
                <div className="empty">Loading keys…</div>
              ) : activeKeys.length === 0 ? (
                <div className="empty">No active keys yet.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {activeKeys.map((k) => (
                    <div key={k.key_id} className="settings-key-row">
                      <code style={{ color: "var(--fg)", fontFamily: "var(--font-mono)", fontSize: 11, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {k.key_id}
                      </code>
                      <span style={{ color: "var(--muted)", fontSize: 10, fontFamily: "var(--font-mono)", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {k.scopes.join(", ")}
                      </span>
                      <span style={{ color: "var(--muted-dim)", fontSize: 10, fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
                        {fmtDate(k.created_at)}
                      </span>
                      <button className="settings-btn danger" onClick={() => revoke(k.key_id)}>
                        Revoke
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Integrations ─────────────────────────────────────────────── */}
        <div className="settings-section">
          <div className="settings-section-label">Integrations</div>
          <div className="fcard" style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {[
              { name: "MCP Server",   blurb: "Tool-call bridge for agent workflows",   status: "active" },
              { name: "Ithaca Docs", blurb: "Documentation and API reference",         status: "active", href: "https://docs.tradeithaca.com" },
            ].map((int, i, arr) => (
              <div key={int.name} style={{
                display: "flex", alignItems: "center", gap: 14,
                padding: "13px 2px",
                borderBottom: i < arr.length - 1 ? "1px solid var(--border-soft)" : "none",
              }}>
                <div style={{
                  width: 34, height: 34, borderRadius: 10,
                  background: "var(--panel-2)", border: "1px solid var(--border)",
                  display: "grid", placeItems: "center", flexShrink: 0, fontSize: 14,
                }}>
                  {int.name === "MCP Server"    ? "⚡" : "📄"}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 550, color: "var(--fg)" }}>{int.name}</div>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 1 }}>{int.blurb}</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    fontSize: 10, fontFamily: "var(--font-mono)",
                    textTransform: "uppercase", letterSpacing: "0.1em",
                    color: int.status === "active" ? "var(--pos)" : "var(--muted-dim)",
                  }}>
                    {int.status}
                  </span>
                  {int.href && (
                    <a href={int.href} target="_blank" rel="noopener noreferrer" className="settings-btn" style={{ textDecoration: "none", padding: "5px 12px", fontSize: 11 }}>
                      Open ↗
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Session ──────────────────────────────────────────────────── */}
        <div className="settings-section">
          <div className="settings-section-label">Session</div>
          <div className="fcard">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
              <div>
                <div style={{ fontSize: 13, color: "var(--fg)", marginBottom: 3 }}>
                  Signed in as <strong style={{ fontWeight: 650 }}>{user.email}</strong>
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)" }}>
                  Session is active
                </div>
              </div>
              <button className="settings-btn danger" onClick={signOut}>
                Sign out
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

function settingsError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  if (/401|unauthorized|sign in/i.test(message)) return "Keys unavailable — re-authenticate.";
  return "Could not update keys.";
}

function isUnauthorized(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  return /401|unauthorized|sign in/i.test(message);
}
