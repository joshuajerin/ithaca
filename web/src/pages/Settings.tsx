import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api";

const SCOPES: { id: string; label: string }[] = [
  { id: "data:read", label: "Read market data" },
  { id: "strategy:author", label: "Author strategies" },
  { id: "runs:write", label: "Create runs" },
  { id: "runs:cancel", label: "Cancel runs" },
  { id: "approvals:read", label: "Read approvals" },
  { id: "approvals:decide", label: "Decide approvals" },
  { id: "artifacts:read", label: "Read artifacts" },
  { id: "deploy:backtest", label: "Run backtests" },
  { id: "deploy:paper", label: "Request paper" },
  { id: "triggers:write", label: "Manage triggers" },
  { id: "providers:write", label: "Manage providers" },
];

const PRESETS: { id: string; label: string; description: string; scopes: string[] }[] = [
  {
    id: "research",
    label: "Research",
    description: "Read tools, sessions, and artifacts.",
    scopes: ["data:read", "artifacts:read"],
  },
  {
    id: "backtest",
    label: "Backtest agent",
    description: "Research, author strategy specs, queue backtests, and cancel runs.",
    scopes: ["data:read", "strategy:author", "runs:write", "runs:cancel", "artifacts:read", "deploy:backtest"],
  },
  {
    id: "paper",
    label: "Paper requester",
    description: "Backtest plus request paper deployments and order-intent previews.",
    scopes: [
      "data:read",
      "strategy:author",
      "runs:write",
      "runs:cancel",
      "approvals:read",
      "artifacts:read",
      "deploy:backtest",
      "deploy:paper",
    ],
  },
  {
    id: "automation",
    label: "Automation",
    description: "Paper requester plus trigger and provider setup.",
    scopes: [
      "data:read",
      "strategy:author",
      "runs:write",
      "runs:cancel",
      "approvals:read",
      "artifacts:read",
      "deploy:backtest",
      "deploy:paper",
      "triggers:write",
      "providers:write",
    ],
  },
  {
    id: "operator",
    label: "Operator",
    description: "Full valid scope set. Approval decisions are still human-session gated.",
    scopes: SCOPES.map((s) => s.id),
  },
];

type KeyRow = { key_id: string; scopes: string[]; created_at: string; revoked: boolean };

function fmtDate(v: string | number): string {
  const d = new Date(typeof v === "number" ? v * 1000 : v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleDateString();
}

export function Settings() {
  const { user, manageAccount, signOut } = useAuth();

  const [keys, setKeys] = useState<KeyRow[]>([]);
  const [loadingKeys, setLoadingKeys] = useState(true);
  const [keysError, setKeysError] = useState<string | null>(null);
  const [selectedScopes, setSelectedScopes] = useState<string[]>(() => PRESETS[2].scopes);
  const [minting, setMinting] = useState(false);
  const [freshKey, setFreshKey] = useState<{ api_key: string; key_id: string } | null>(null);
  const [copied, setCopied] = useState(false);

  async function loadKeys() {
    setLoadingKeys(true);
    setKeysError(null);
    try {
      setKeys(await api.listKeys());
    } catch (e) {
      if (isUnauthorized(e)) {
        setKeys([]);
      } else {
        setKeysError("Could not update keys.");
      }
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

  function applyPreset(scopes: string[]) {
    setSelectedScopes(scopes);
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

  if (!user) return null;
  const initials = user.name.split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
  const activeKeys = keys.filter((k) => !k.revoked);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="page-title">Settings</div>
        </div>
      </div>

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
          <button className="btn" onClick={manageAccount}>
            Manage
          </button>
        </div>
      </section>

      <section className="set-section">
        <div className="set-h">Agent access</div>
        <div className="set-card">
          <div className="set-field">
            <label>Preset</label>
            <div className="preset-grid">
              {PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  className={`preset-btn ${sameScopes(selectedScopes, preset.scopes) ? "active" : ""}`}
                  onClick={() => applyPreset(preset.scopes)}
                  type="button"
                >
                  <span>{preset.label}</span>
                  <small>{preset.description}</small>
                </button>
              ))}
            </div>
          </div>

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
                {minting ? "Generating..." : "Generate key"}
              </button>
            </div>
          </div>

          {freshKey && (
            <div className="set-field key-fresh">
              <label>New key</label>
              <code className="mono set-value key-plain">{freshKey.api_key}</code>
              <div className="set-actions">
                <button className="btn primary" onClick={copyFresh}>
                  {copied ? "Copied" : "Copy key"}
                </button>
              </div>
            </div>
          )}

          <div className="set-hint">
            Agent keys can request paper work and create order intents, but approval decisions
            and paper lifecycle promotion still require a signed-in human session.
          </div>

          {keysError && <div className="set-hint err">{keysError}</div>}

          <div className="set-field">
            <label>Active keys</label>
            {loadingKeys ? (
              <div className="set-hint">Loading...</div>
            ) : activeKeys.length === 0 ? (
              <div className="set-hint">No keys.</div>
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
        </div>
      </section>

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

function sameScopes(a: string[], b: string[]) {
  return a.length === b.length && a.every((scope) => b.includes(scope));
}

function settingsError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  if (/401|unauthorized|sign in/i.test(message)) return "Keys unavailable.";
  return "Could not update keys.";
}

function isUnauthorized(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  return /401|unauthorized|sign in/i.test(message);
}
