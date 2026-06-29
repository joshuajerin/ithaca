import { useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { api, type AgentToolkitsCatalog, type AgentToolkitsError } from "../api";
import { MCP_BASE } from "../config";
import { useAsync } from "../hooks/useAsync";

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
  const catalog = useAsync<AgentToolkitsCatalog>(
    (signal) => user ? api.listAgentToolkits(signal) : Promise.resolve({ source: "live", toolkits: [] }),
    [user?.id],
  );

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
        <div className="set-h">Doomberg MCP</div>
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
          <ToolkitCatalog catalog={catalog} />
          <div className="set-hint">
            Approving creates a scoped MCP key for this tenant and sends it to the local
            installer waiting on your machine. The key can research, queue backtests, and
            request paper work; promotion, approval decisions, and any live deployment still
            require a signed-in human.
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
                Doomberg MCP is installed. You can close this tab and return to the coding agent.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function ToolkitCatalog({ catalog }: {
  catalog: {
    data: AgentToolkitsCatalog | null;
    loading: boolean;
    error: string | null;
    reload: () => void;
  };
}) {
  const toolkits = catalog.data?.toolkits ?? [];
  const toolsShown = toolkits.reduce((sum, toolkit) => (
    sum + toolkit.direct_tools.length + toolkit.tools.length
  ), 0);

  return (
    <div className="agent-toolkit-catalog">
      <div className="agent-toolkit-head">
        <div>
          <div className="agent-toolkit-title">Live tool catalog</div>
          <div className="agent-toolkit-meta">
            {catalog.loading
              ? "Loading server catalog..."
              : catalog.error
                ? catalogMessage(catalog.error)
                : `${toolkits.length} toolkits · ${toolsShown} listed tools`}
          </div>
        </div>
        <button className="btn" onClick={catalog.reload} disabled={catalog.loading}>Refresh</button>
      </div>

      {catalog.loading ? (
        <div className="empty">Loading toolkits...</div>
      ) : catalog.error ? (
        <div className={`agent-toolkit-state ${catalogStateClass(catalog.error)}`}>
          <div>{catalogMessage(catalog.error)}</div>
          <div className="agent-toolkit-state-detail">{catalogDetail(catalog.error)}</div>
        </div>
      ) : toolkits.length === 0 ? (
        <div className="agent-toolkit-state empty-state">
          <div>No tools published.</div>
          <div className="agent-toolkit-state-detail">
            The server catalog responded, but it did not include any toolkits or tools.
          </div>
        </div>
      ) : (
        <div className="agent-toolkit-list">
          {toolkits.map((toolkit) => (
            <div className="agent-toolkit-row" key={toolkit.toolkit_id}>
              <div className="agent-toolkit-row-head">
                <div>
                  <div className="agent-toolkit-name">{toolkit.name}</div>
                  <div className="agent-toolkit-id">{toolkit.toolkit_id}</div>
                </div>
                <div className="agent-toolkit-counts">
                  <span>{toolkit.direct_tool_count} direct</span>
                  {typeof toolkit.skill_count === "number" && <span>{toolkit.skill_count} skills</span>}
                </div>
              </div>
              {toolkit.description && <div className="agent-toolkit-desc">{toolkit.description}</div>}
              {toolkit.required_first_tool && (
                <div className="agent-toolkit-first">
                  Start with <code>{toolkit.required_first_tool}</code>
                </div>
              )}
              {toolkit.direct_tools.length > 0 || toolkit.tools.length > 0 ? (
                <div className="agent-tool-list">
                  {toolkit.direct_tools.map((tool) => (
                    <code key={`direct-${tool}`} className="agent-tool-chip">{tool}</code>
                  ))}
                  {toolkit.tools.map((tool) => (
                    <div key={`tool-${tool.name}`} className="agent-tool-chip rich">
                      <code>{tool.name}</code>
                      {tool.description && <span>{tool.description}</span>}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="agent-toolkit-state-detail">
                  Toolkit details were not included by the server catalog.
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function catalogKind(message: string): AgentToolkitsError["kind"] | "unknown" {
  if (/auth-required/i.test(message) || /401|403|unauthorized|forbidden|sign in/i.test(message)) return "auth-required";
  if (/No REST agent toolkit catalog endpoint/i.test(message)) return "unavailable";
  return "fetch-failed";
}

function catalogMessage(error: string): string {
  switch (catalogKind(error)) {
    case "auth-required":
      return "Sign in required for the live catalog.";
    case "unavailable":
      return "Live catalog endpoint is not exposed by this backend.";
    case "fetch-failed":
    default:
      return "Could not fetch the live tool catalog.";
  }
}

function catalogDetail(error: string): string {
  switch (catalogKind(error)) {
    case "auth-required":
      return "Re-authenticate, then refresh this catalog before approving the installer.";
    case "unavailable":
      return "The UI is ready to render server toolkits, but REST does not currently expose the MCP catalog.";
    case "fetch-failed":
    default:
      return error;
  }
}

function catalogStateClass(error: string): string {
  return catalogKind(error) === "auth-required" ? "auth" : "err";
}
