import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { beginOAuth, providerConfigured, type Provider } from "../auth/oauth";
import { GoogleIcon, GithubIcon } from "../auth/icons";
import { api } from "../api";

const PROVIDERS: { id: Provider; label: string; icon: () => JSX.Element; blurb: string }[] = [
  { id: "google", label: "Google", icon: GoogleIcon, blurb: "Sign-in & identity" },
  { id: "github", label: "GitHub", icon: GithubIcon, blurb: "Sign-in & repo-linked strategies" },
];

function maskToken(t: string): string {
  return `${t.slice(0, 7)}${"•".repeat(18)}${t.slice(-4)}`;
}

export function Settings() {
  const { user, integrations, setIntegration, signOut } = useAuth();
  const [token] = useState<string>(
    () => localStorage.getItem("doomberg.token") ?? "",
  );
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);

  function copyToken() {
    navigator.clipboard?.writeText(token).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  }

  function toggleProvider(p: Provider, connected: boolean) {
    if (!connected && providerConfigured(p)) {
      beginOAuth(p, "link"); // real link flow → returns through the callback
      return;
    }
    setIntegration(p, !connected); // demo toggle when no client id is set
  }

  if (!user) return null;
  const initials = user.name.split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

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
                  onClick={() => toggleProvider(id, connected)}
                >
                  {connected ? "Disconnect" : "Connect"}
                </button>
              </div>
            );
          })}
        </div>
      </section>

      {/* API / MCP access */}
      <section className="set-section">
        <div className="set-h">Agent access (MCP)</div>
        <div className="set-card">
          <div className="set-field">
            <label>Tenant</label>
            <code className="mono set-value">{api.tenantId}</code>
          </div>
          {token ? (
            <>
              <div className="set-field">
                <label>Key ID</label>
                <code className="mono set-value">{token.split("_")[2] ?? "—"}</code>
              </div>
              <div className="set-field">
                <label>Bearer token</label>
                <code className="mono set-value">{revealed ? token : maskToken(token)}</code>
                <div className="set-actions">
                  <button className="btn" onClick={() => setRevealed((v) => !v)}>
                    {revealed ? "Hide" : "Reveal"}
                  </button>
                  <button className="btn" onClick={copyToken}>
                    {copied ? "Copied" : "Copy"}
                  </button>
                  <button className="btn" onClick={signOut}>
                    Sign out and reconnect
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="set-hint">No bearer token — sign in via OAuth to mint one.</div>
          )}
          <div className="set-hint">
            Point your agent at <code>{api.apiBase.replace("/api", "")}/mcp</code> with this token
            as the bearer. Read + propose_strategy scopes only — it can never move money.
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
