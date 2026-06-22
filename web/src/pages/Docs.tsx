import type { CSSProperties } from "react";

type DocGroup = {
  heading: string;
  entries: Array<{
    title: string;
    path: string;
    note: string;
  }>;
};

const CODE_FILES = [
  { title: "REST Gateway API", path: "services/rest-gateway/src/doomberg_rest/app.py", note: "auth, sessions, runs, strategies, SSE events" },
  { title: "MCP Gateway", path: "services/mcp-gateway/src/doomberg_mcp/server.py", note: "tools + streamable MCP context + tracing" },
  { title: "MCP HTTP Auth", path: "services/mcp-gateway/src/doomberg_mcp/http.py", note: "bearer validation + scope gate for hosted clients" },
  { title: "Platform Core", path: "services/platform/src/doomberg_platform/platform.py", note: "shared stores + tenant isolation entrypoint" },
  { title: "Trace Store", path: "services/platform/src/doomberg_platform/trace_store.py", note: "gap-free event timeline persisted for sessions" },
  { title: "Run/Strategy API", path: "services/platform/src/doomberg_platform/run_store.py", note: "state machine, audit metadata, run lifecycle" },
  { title: "Auth Store", path: "services/platform/src/doomberg_platform/auth_store.py", note: "tenant API key format + scope checks" },
  { title: "User Store", path: "services/platform/src/doomberg_platform/user_store.py", note: "signup/signin/session hashing + tenancy lookups" },
];

const SKILLSET_DOCS: DocGroup[] = [
  {
    heading: "Skillsets",
    entries: [
      { title: "market skillset", path: "docs/plans/dashboard-sessions-ui.md", note: "market dashboard/session tree reference" },
      { title: "strategy skillset", path: "services/mcp-gateway/src/doomberg_mcp/_skillsets/strategy.py", note: "strategy authoring + backtest/paper lifecycle" },
      { title: "data skillset", path: "services/mcp-gateway/src/doomberg_mcp/_skillsets/data.py", note: "market/instrument fetch helpers and normalizations" },
      { title: "financials skillset", path: "services/mcp-gateway/src/doomberg_mcp/_skillsets/financials.py", note: "fundamentals, valuation surfaces, filings" },
    ],
  },
  {
    heading: "Documentation",
    entries: [
      { title: "Onboarding", path: "docs/ONBOARDING.md", note: "tenant/key creation, scope semantics, operational loop" },
      { title: "Master Plan", path: "docs/plans/doomberg-v2/MASTER-PLAN.md", note: "architecture and milestone plan" },
      { title: "Data Strategy", path: "docs/plans/doomberg-v2/DATA-SOURCING-STRATEGY.md", note: "datasource and ingestion model" },
      { title: "Design Notes", path: "docs/plans/doomberg-v2/designs/webui.md", note: "web observability and workflow rendering" },
    ],
  },
];

export function Docs() {
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="page-title">Docs</div>
          <div className="page-sub">code files · skillset modules · markdown references</div>
        </div>
      </div>

      <section className="dash-section docs-group">
        <div className="section-head"><span>Code Files</span><span>{CODE_FILES.length}</span></div>
        <div style={gridStyle}>
          {CODE_FILES.map((entry) => (
            <article className="code-card" key={entry.path}>
              <div className="page-sub" style={{ marginBottom: 4 }}>{entry.title}</div>
              <a href={entry.path} className="mono code-path">{entry.path}</a>
              <p className="page-sub" style={{ marginTop: 8, marginBottom: 0 }}>{entry.note}</p>
            </article>
          ))}
        </div>
      </section>

      {SKILLSET_DOCS.map((group) => (
        <section className="dash-section docs-group" key={group.heading}>
          <div className="section-head">
            <span>{group.heading}</span>
            <span>{group.entries.length}</span>
          </div>
          <div style={gridStyle}>
            {group.entries.map((entry) => (
              <article className="code-card" key={entry.path}>
                <div className="page-sub" style={{ marginBottom: 4 }}>{entry.title}</div>
                <a href={entry.path} className="mono code-path">{entry.path}</a>
                <p className="page-sub" style={{ marginTop: 8, marginBottom: 0 }}>{entry.note}</p>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

const gridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
  gap: 12,
};
