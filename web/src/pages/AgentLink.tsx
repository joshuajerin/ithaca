import { useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api";
import { MCP_BASE } from "../config";

const DEFAULT_SCOPES = [
  "agent:read",
  "data:read",
  "strategy:author",
  "runs:write",
  "runs:cancel",
  "approvals:read",
  "artifacts:read",
  "deploy:backtest",
  "deploy:paper",
];

const ACCESS_ITEMS = [
  {
    title: "Access market data",
    detail: "Quotes, history, news, filings, and saved datasets.",
  },
  {
    title: "Run research tools",
    detail: "Create MCP sessions and read generated artifacts.",
  },
  {
    title: "Draft strategies",
    detail: "Author specs and prepare backtest inputs.",
  },
  {
    title: "Queue backtests",
    detail: "Run historical and paper-mode simulations.",
  },
  {
    title: "Request deployments",
    detail: "Live promotion still requires your approval.",
  },
];

function param(name: string): string {
  const searchValue = new URLSearchParams(window.location.search).get(name);
  if (searchValue) return searchValue;
  return new URLSearchParams(window.location.hash.split("?", 2)[1] ?? "").get(name) ?? "";
}

export function AgentLink() {
  const { user } = useAuth();
  const [status, setStatus] = useState<"idle" | "working" | "done" | "denied" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const config = useMemo(() => {
    const callback = param("callback");
    const state = param("state");
    const mcpUrl = param("mcp_url") || MCP_BASE;
    const name = param("name") || "Ithaca";
    const client = param("client") || "codex";
    const auth = param("auth") || "";
    return { callback, state, mcpUrl, name, client, auth };
  }, []);

  async function approve() {
    setStatus("working");
    setError(null);
    try {
      if (!config.callback || !config.state) {
        throw new Error("Installer callback is missing. Start from the install command again.");
      }
      const key = await api.mintKey(DEFAULT_SCOPES);
      const res = await fetch(config.callback, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          state: config.state,
          api_key: key.api_key,
          key_id: key.key_id,
          tenant_id: key.tenant_id,
          scopes: key.scopes,
          mcp_url: config.mcpUrl,
        }),
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`Installer callback failed (${res.status})${body ? `: ${body}` : ""}`);
      }
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  async function deny() {
    setStatus("working");
    setError(null);
    try {
      if (config.callback && config.state) {
        await fetch(config.callback, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            state: config.state,
            denied: true,
            error: "User denied Ithaca compatibility-key access.",
            mcp_url: config.mcpUrl,
          }),
        }).catch(() => undefined);
      }
      setStatus("denied");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  if (!user) return null;
  const nativeClient = ["codex", "claude-code", "cursor"].includes(config.client);
  const compatibilityRequested = config.auth === "api-key";

  return (
    <div className="agent-consent-page">
      <main className="agent-consent-card" aria-labelledby="agent-consent-title">
        <header className="agent-consent-header">
          <h1 id="agent-consent-title">
            Create an Ithaca compatibility key
          </h1>
          <p>
            This creates a scoped automation key for <strong>{config.name}</strong>.
          </p>
        </header>

        {nativeClient && !compatibilityRequested ? (
          <div className="agent-consent-message">
            Codex, Claude Code, and Cursor use Clerk OAuth. Return to Settings and add the MCP URL instead of creating an API key.
          </div>
        ) : <section className="agent-consent-access" aria-label="Requested access">
          <div className="agent-consent-eyebrow">Your account will be used to</div>
          <div className="agent-consent-list">
            {ACCESS_ITEMS.map((item) => (
              <div className="agent-consent-access-row" key={item.title}>
                <span className="agent-consent-check" aria-hidden="true">✓</span>
                <div>
                  <div className="agent-consent-access-title">{item.title}</div>
                  <div className="agent-consent-access-detail">{item.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </section>}

        <div className="agent-consent-meta">
          <span>Account</span>
          <strong>{user.email}</strong>
        </div>

        {error && <div className="agent-consent-message err">{error}</div>}
        {status === "done" && (
          <div className="agent-consent-message ok">
            Compatibility key created. You can close this tab and return to the agent.
          </div>
        )}
        {status === "denied" && (
          <div className="agent-consent-message">
            Access denied. No Ithaca MCP key was created for this agent.
          </div>
        )}

        <div className="agent-consent-actions">
          <button
            className="agent-consent-button deny"
            onClick={deny}
            disabled={nativeClient && !compatibilityRequested || status === "working" || status === "done" || status === "denied"}
          >
            Deny
          </button>
          <button
            className="agent-consent-button approve"
            onClick={approve}
            disabled={status === "working" || status === "done" || status === "denied"}
          >
            {status === "working" ? "Creating..." : status === "done" ? "Created" : "Create compatibility key"}
          </button>
        </div>
      </main>
    </div>
  );
}
