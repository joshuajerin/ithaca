import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export function NewSession() {
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function submit() {
    const clean = prompt.trim();
    if (!clean) {
      setError("Prompt is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const session = await api.createSession(clean, title.trim() || undefined);
      navigate(`/sessions/${session.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page new-session-page">
      <div className="page-head">
        <div>
          <div className="page-title">New Session</div>
          <div className="page-sub">capture the prompt, then attach MCP tool calls to the trace</div>
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

        <label className="set-h" htmlFor="session-prompt">Prompt</label>
        <textarea
          id="session-prompt"
          className="prompt-textarea"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="user: what does nvda look like"
        />

        {error && <div className="banner">{error}</div>}

        <div className="set-actions">
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? "Opening..." : "Open Session"}
          </button>
        </div>
      </section>

      <section className="dash-section wide">
        <div className="section-head">
          <span>Attach An Agent</span>
          <span>MCP</span>
        </div>
        <div className="mcp-lines">
          <div className="kv"><span className="k">endpoint</span> https://mcp.doomberg.me/mcp</div>
          <div className="kv"><span className="k">auth</span> Authorization: Bearer dmbg_...</div>
          <div className="kv"><span className="k">context</span> call session_context with this session id after opening</div>
          <div className="kv"><span className="k">trace</span> tool calls stream into Sessions in real time</div>
        </div>
      </section>
    </div>
  );
}

