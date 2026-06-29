import { useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api";
import { MCP_BASE } from "../config";

const DEFAULT_SCOPES = [
  "data:read",
  "strategy:author",
  "runs:write",
  "runs:cancel",
  "approvals:read",
  "artifacts:read",
  "deploy:backtest",
  "deploy:paper",
];

function param(name: string): string {
  return new URLSearchParams(window.location.hash.split("?", 2)[1] ?? "").get(name) ?? "";
}

export function AgentLink() {
  const { user } = useAuth();
  const [status, setStatus] = useState<"idle" | "working" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const config = useMemo(() => {
    const callback = param("callback");
    const state = param("state");
    const mcpUrl = param("mcp_url") || MCP_BASE;
    const name = param("name") || "doomberg";
    const client = param("client") || "codex";
    return { callback, state, mcpUrl, name, client };
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

  if (!user) return null;

  return (
    <div className="page agent-link-page">
      <div className="page-head">
        <div>
          <div className="page-title">Connect agent</div>
          <div className="page-sub">mcp · {config.client}</div>
        </div>
      </div>
      <section className="set-section">
        <div className="set-h">Ithaca MCP</div>
        <div className="set-card">
          <div className="set-field">
            <label>Agent config</label>
            <div className="agent-link-summary">
              <div>
                <span>Name</span>
                <code className="mono">{config.name}</code>
              </div>
              <div>
                <span>Endpoint</span>
                <code className="mono">{config.mcpUrl}</code>
              </div>
              <div>
                <span>Account</span>
                <code className="mono">{user.email}</code>
              </div>
            </div>
          </div>
          <div className="set-hint">
            Approving creates a scoped MCP key for this tenant and sends it to the local
            installer waiting on your machine. The key can run research, backtests, and paper
            trading; it cannot request live deployment.
          </div>
          {error && <div className="set-hint err">{error}</div>}
          <div className="set-field">
            <div className="set-actions">
              <button className="btn primary" onClick={approve} disabled={status === "working" || status === "done"}>
                {status === "working" ? "Connecting..." : status === "done" ? "Connected" : "Approve"}
              </button>
            </div>
            {status === "done" && (
              <div className="set-hint">
                Ithaca MCP is installed. You can close this tab and return to the coding agent.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
