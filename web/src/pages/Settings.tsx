import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { beginOAuth, providerConfigured, type Provider } from "../auth/oauth";
import { GoogleIcon, GithubIcon } from "../auth/icons";
import { api } from "../api";
import { MCP_BASE } from "../config";

const PROVIDERS: { id: Provider; label: string; icon: () => JSX.Element; blurb: string }[] = [
  { id: "google", label: "Google", icon: GoogleIcon, blurb: "Sign-in & identity" },
  { id: "github", label: "GitHub", icon: GithubIcon, blurb: "Sign-in & repo-linked strategies" },
];

// The issuable agent scopes. Trading scopes are intentionally absent.
const SCOPES: { id: string; label: string }[] = [
  { id: "data:read", label: "Read market & research data" },
  { id: "strategy:author", label: "Author / propose strategies" },
  { id: "runs:write", label: "Create durable runs" },
  { id: "runs:cancel", label: "Cancel durable runs" },
  { id: "approvals:read", label: "Read approvals" },
  { id: "artifacts:read", label: "Read artifacts" },
  { id: "deploy:backtest", label: "Run backtests" },
];

type KeyRow = { key_id: string; scopes: string[]; created_at: string; revoked: boolean };

function fmtDate(v: string | number): string {
  const d = new Date(typeof v === "number" ? v * 1000 : v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleDateString();
}

export function Settings() {
  const { user, integrations, setIntegration, signOut } = useAuth();

  const [keys, setKeys] = useState<KeyRow[]>([]);
  const [loadingKeys, setLoadingKeys] = useState(true);
  const [keysError, setKeysError] = useState<string | null>(null);
  const [selectedScopes, setSelectedScopes] = useState<string[]>(() => SCOPES.map((s) => s.id));
  const [minting, setMinting] = useState(false);
  const [freshKey, setFreshKey] = useState<{ api_key: string; key_id: string } | null>(null);
  const [copied, setCopied] = useState(false);

  async function loadKeys() {
    setLoadingKeys(true);
    setKeysError(null);
    try {
      setKeys(await api.listKeys());
    } catch (e) {
      setKeysError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingKeys(false);
    }
  }

  useEffect(() => {
    void loadKeys();
  }, []);

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
      setKeysError(e instanceof Error ? e.message : String(e));
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
      setKeysError(e instanceof Error ? e.message : String(e));
    }
  }

  function copyFresh() {
    if (!freshKey) return;
    navigator.clipboard?.writeText(freshKey.api_key).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  }

  if (!user) return null;
  const initials = user.name.split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
  const activeKeys = keys.filter((k) => !k.revoked);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="page-title">Settings</div>
          <div className="page-sub">account · integrations · access</div>
        </div>
      </div>

      {/* Profile */}
      <section className="set-section">
        <div className="set-h">Profile</div>
        <div className="set-card profile-row">
          <div className="avatar">
            {user.avatarUrl ? <img src={user.avatarUrl} alt="" /> : <span>{initials}</span>}
          </div>
          <div className="profile-meta">
            <div className="profile-name">{user.name}</div>
            <div className="profile-email">{user.email}</div>
          </div>
          <span className="badge">{user.provider}</span>
        </div>
      </section>

      {/* Connected accounts / OAuth integrations */}
      <section className="set-section">
        <div className="set-h">Connected accounts</div>
        <div className="set-card">
          {PROVIDERS.map(({ id, label, icon: Icon, blurb }) => {
            const connected = integrations[id];
            return (
              <div key={id} className="integration-row">
                <span className="int-icon"><Icon /></span>
                <div className="int-meta">
                  <div className="int-name">{label}</div>
                  <div className="int-blurb">{blurb}</div>
                </div>
                <span className={`int-status ${connected ? "on" : "off"}`}>
                  {connected ? "Connected" : "Not connected"}
                </span>
                <button
                  className={`btn ${connected ? "" : "primary"}`}
                  onClick={() => {
                    if (!connected && providerConfigured(id)) {
                      beginOAuth(id, "link");
                      return;
                    }
                    setIntegration(id, !connected);
                  }}
                >
                  {connected ? "Disconnect" : "Connect"}
                </button>
              </div>
            );
          })}
        </div>
      </section>

      {/* API / MCP access — mint bearer keys for BYO agents */}
      <section className="set-section">
        <div className="set-h">Agent access (MCP)</div>
        <div className="set-card">
          <div className="set-field">
            <label>Tenant</label>
            <code className="mono set-value">{api.tenantId}</code>
          </div>
          <div className="set-field">
            <label>Endpoint</label>
            <code className="mono set-value">{MCP_BASE}</code>
          </div>

          {/* Scope picker + generate */}
          <div className="set-field">
            <label>Scopes</label>
            <div className="scope-grid">
              {SCOPES.map((s) => (
                <label key={s.id} className="scope-opt">
                  <input
                    type="checkbox"
                    checked={selectedScopes.includes(s.id)}
                    onChange={() => toggleScope(s.id)}
                  />
                  <span>{s.label}</span>
                  <code className="mono scope-id">{s.id}</code>
                </label>
              ))}
            </div>
            <div className="set-actions">
              <button
                className="btn primary"
                onClick={generateKey}
                disabled={minting || selectedScopes.length === 0}
              >
                {minting ? "Generating…" : "Generate MCP key"}
              </button>
            </div>
          </div>

          {/* Freshly-minted plaintext — shown ONCE */}
          {freshKey && (
            <div className="set-field key-fresh">
              <label>New key — copy it now, it won't be shown again</label>
              <code className="mono set-value key-plain">{freshKey.api_key}</code>
              <div className="set-actions">
                <button className="btn primary" onClick={copyFresh}>
                  {copied ? "Copied" : "Copy key"}
                </button>
              </div>
            </div>
          )}

          {keysError && <div className="set-hint err">{keysError}</div>}

          {/* Existing keys */}
          <div className="set-field">
            <label>Active keys</label>
            {loadingKeys ? (
              <div className="set-hint">Loading…</div>
            ) : activeKeys.length === 0 ? (
              <div className="set-hint">No keys yet — generate one above for your agent.</div>
            ) : (
              <div className="key-list">
                {activeKeys.map((k) => (
                  <div key={k.key_id} className="key-row">
                    <code className="mono key-id">{k.key_id}</code>
                    <span className="key-scopes">{k.scopes.join(", ")}</span>
                    <span className="key-date">{fmtDate(k.created_at)}</span>
                    <button className="btn" onClick={() => revoke(k.key_id)}>
                      Revoke
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="set-hint">
            Hand this key to your agent as the <code>Authorization: Bearer</code> token against{" "}
            <code>{MCP_BASE}</code>. Keys can read data, author strategies, and run
            backtests. Trading is disabled in this workspace.
          </div>
        </div>
      </section>

      {/* Danger / session */}
      <section className="set-section">
        <div className="set-h">Session</div>
        <div className="set-card set-row-end">
          <span className="set-hint">Signed in as {user.email}.</span>
          <button className="btn" onClick={signOut}>
            Sign out
          </button>
        </div>
      </section>
    </div>
  );
}
