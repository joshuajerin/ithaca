import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { RunRow } from "../types";

const MCP_URL = "https://mcp.doomberg.me/mcp";
const MCP_SCOPES = ["data:read", "strategy:author", "deploy:backtest", "deploy:paper"];

export function NewSession() {
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<RunRow | null>(null);
  const [agentKey, setAgentKey] = useState<string | null>(null);
  const [keyBusy, setKeyBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const navigate = useNavigate();

  const cleanTitle = title.trim();
  const contextPayload = created ? {
    name: "session_context",
    arguments: {
      session_id: created.id,
      prompt: "<your prompt from chat>",
      title: cleanTitle || "Realtime session",
    },
  } : null;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const session = await api.createSession("", cleanTitle || undefined);
      setCreated(session);
      setAgentKey(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function generateAgentKey() {
    setKeyBusy(true);
    setError(null);
    try {
      const res = await api.mintKey(MCP_SCOPES);
      setAgentKey(res.api_key);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setKeyBusy(false);
    }
  }

  function copy(label: string, value: string) {
    navigator.clipboard?.writeText(value).then(() => {
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1400);
    });
  }

  return (
    <div className="page new-session-page">
      <div className="page-head">
        <div>
          <div className="page-title">New Session</div>
          <div className="page-sub">start a realtime MCP trace; the prompt arrives from chat</div>
        </div>
      </div>

      <section className="prompt-editor">
        <label className="set-h" htmlFor="session-title">Title</label>
        <input
          id="session-title"
          className="auth-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="NVDA scan"
        />

        <div className="realtime-start">
          <div className="set-h">Realtime run</div>
          <div className="set-hint no-pad">
            Start the session here, then prompt your agent from chat. The first MCP
            <code> session_context </code> call records that prompt and every skill call streams
            into the live trace.
          </div>
        </div>

        {error && <div className="banner">{error}</div>}

        <div className="set-actions">
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? "Starting..." : "Start Realtime Session"}
          </button>
          {created && (
            <button className="btn" onClick={() => navigate(`/sessions/${created.id}`)}>
              Open Live Trace
            </button>
          )}
        </div>
      </section>

      {created && contextPayload && (
        <section className="dash-section wide handoff-card">
          <div className="section-head">
            <span>Agent handoff</span>
            <span>same tenant</span>
          </div>
          <div className="handoff-grid">
            <div className="handoff-block">
              <div className="set-h">Session</div>
              <div className="kv"><span className="k">id</span> {created.id}</div>
              <div className="kv"><span className="k">endpoint</span> {MCP_URL}</div>
              <div className="kv"><span className="k">stream</span> /sessions/{created.id}</div>
              <div className="set-actions">
                <button className="btn" onClick={() => copy("session", created.id)}>
                  {copied === "session" ? "Copied" : "Copy session id"}
                </button>
              </div>
            </div>
            <div className="handoff-block">
              <div className="set-h">First MCP call</div>
              <pre className="pre handoff-pre">{JSON.stringify(contextPayload, null, 2)}</pre>
              <div className="set-actions">
                <button className="btn" onClick={() => copy("context", JSON.stringify(contextPayload, null, 2))}>
                  {copied === "context" ? "Copied" : "Copy context"}
                </button>
              </div>
            </div>
            <div className="handoff-block">
              <div className="set-h">Auth</div>
              <div className="set-hint no-pad">
                Generate a key while signed in. The key belongs to this same account/tenant, so any MCP
                tool calls after <code>session_context</code> stream into this session in real time.
              </div>
              <div className="set-actions">
                <button className="btn primary" onClick={generateAgentKey} disabled={keyBusy}>
                  {keyBusy ? "Generating..." : "Generate session MCP key"}
                </button>
              </div>
              {agentKey && (
                <>
                  <code className="mono set-value key-plain">{agentKey}</code>
                  <div className="set-actions">
                    <button className="btn" onClick={() => copy("key", agentKey)}>
                      {copied === "key" ? "Copied" : "Copy key"}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </section>
      )}

      <section className="dash-section wide">
        <div className="section-head">
          <span>Attach An Agent</span>
          <span>MCP</span>
        </div>
        <div className="mcp-lines">
          <div className="kv"><span className="k">endpoint</span> {MCP_URL}</div>
          <div className="kv"><span className="k">auth</span> Authorization: Bearer dmbg_...</div>
          <div className="kv"><span className="k">context</span> call session_context with this session id after opening</div>
          <div className="kv"><span className="k">trace</span> tool calls stream into Sessions in real time</div>
        </div>
      </section>
    </div>
  );
}
