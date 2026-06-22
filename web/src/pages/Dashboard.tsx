import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { RunRow, SessionRow, StrategyRow } from "../types";
import { fmtTime, shortId, stateClass } from "../lib/format";

const PRICE_POINTS = [884, 890, 887, 901, 916, 924, 912, 932, 940, 948, 944, 956];

const NEWS = [
  ["09:42", "NVDA", "Supplier checks point to another accelerator allocation step-up."],
  ["09:18", "AMD", "Street desks compare MI-series lead times against hyperscaler capex."],
  ["08:55", "TSM", "Capacity commentary keeps advanced packaging at the center of the tape."],
  ["08:21", "MSFT", "AI infrastructure basket opens firm as rate expectations fade."],
];

const FLOW = [
  ["NVDA", "calls", "$24.8M", "+18%"],
  ["SMH", "puts", "$8.1M", "-4%"],
  ["TSLA", "calls", "$11.6M", "+7%"],
  ["META", "stock", "$31.2M", "+3%"],
];

const SUBWIDGETS = [
  { label: "Risk", value: "0.72", sub: "beta adj", tone: "warn" },
  { label: "IV Rank", value: "61", sub: "30d pct", tone: "run" },
  { label: "Breadth", value: "58%", sub: "advancers", tone: "ok" },
  { label: "Short", value: "1.1%", sub: "float", tone: "" },
];

export function Dashboard() {
  const sessions = useAsync<SessionRow[]>((s) => api.listSessions(s), []);
  const backtests = useAsync<RunRow[]>((s) => api.listRuns("backtest", s), []);
  const paper = useAsync<RunRow[]>((s) => api.listRuns("paper", s), []);
  const strategies = useAsync<StrategyRow[]>((s) => api.listStrategies(s), []);

  const latestSessions = (sessions.data ?? []).slice(-4).reverse();
  const active = (sessions.data ?? []).filter((r) => r.state === "running").length;
  const runCount = (backtests.data?.length ?? 0) + (paper.data?.length ?? 0);
  const lastSession = latestSessions[0];
  const deployed = [...(paper.data ?? []), ...(backtests.data ?? [])].slice(-5).reverse();

  return (
    <div className="page terminal-page">
      <div className="terminal-topbar">
        <div>
          <div className="page-title">Dashboard</div>
          <div className="page-sub">market terminal · stock tape · agent subwidgets</div>
        </div>
        <div className="terminal-actions">
          <span className="ticker-chip">NVDA</span>
          <span className="ticker-chip">SMH</span>
          <Link to="/new-session" className="btn primary">New Session</Link>
        </div>
      </div>

      <div className="terminal-grid">
        <section className="terminal-panel price-panel">
          <PanelHead title="Price Chart" meta="NVDA · 1D" />
          <div className="price-shell">
            <div>
              <div className="price-symbol">NVDA</div>
              <div className="page-sub">NVIDIA Corporation · Nasdaq</div>
            </div>
            <div className="price-quote">
              <div className="price-last">956.30</div>
              <div className="price-change">+12.48 (+1.32%)</div>
            </div>
          </div>
          <svg className="price-chart" viewBox="0 0 600 210" role="img" aria-label="NVDA intraday price chart">
            <defs>
              <linearGradient id="priceFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="rgba(72, 92, 17, 0.26)" />
                <stop offset="100%" stopColor="rgba(72, 92, 17, 0)" />
              </linearGradient>
            </defs>
            {[0, 1, 2, 3, 4].map((i) => (
              <line key={`h-${i}`} x1="0" x2="600" y1={30 + i * 38} y2={30 + i * 38} />
            ))}
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <line key={`v-${i}`} y1="18" y2="196" x1={i * 120} x2={i * 120} />
            ))}
            <polyline points={chartPath(PRICE_POINTS)} />
            <polygon points={`0,198 ${chartPath(PRICE_POINTS)} 600,198`} />
          </svg>
          <div className="range-row">
            {["1D", "1W", "1M", "3M", "6M", "1Y"].map((range) => (
              <button className={range === "1D" ? "active" : ""} key={range}>{range}</button>
            ))}
          </div>
        </section>

        <section className="terminal-panel">
          <PanelHead title="Session Tape" meta={`${active} active`} />
          {sessions.error && <div className="banner">Failed to load sessions: {sessions.error}</div>}
          {sessions.loading && <div className="empty">Loading sessions...</div>}
          {!sessions.loading && latestSessions.length === 0 && (
            <div className="empty">No sessions yet. Start one from New Session.</div>
          )}
          {latestSessions.map((row) => (
            <Link to={`/sessions/${row.id}`} className="terminal-list-row" key={row.id}>
              <div>
                <div className="terminal-row-title">{row.title || row.prompt || "Untitled session"}</div>
                <div className="page-sub">{shortId(row.id)} · {row.call_count ?? 0} calls · {fmtTime(row.last_event_at ?? row.created_at)}</div>
              </div>
              <span className={`badge ${stateClass(row.state)}`}>{row.state}</span>
            </Link>
          ))}
        </section>

        <section className="terminal-panel">
          <PanelHead title="Subwidgets" meta="agent context" />
          <div className="mini-grid">
            <Mini label="Sessions" value={sessions.data?.length ?? 0} sub="research" />
            <Mini label="Runs" value={runCount} sub="deploy queue" />
            <Mini label="Ideas" value={strategies.data?.length ?? 0} sub="strategy specs" />
            <Mini label="Last" value={lastSession ? fmtTime(lastSession.created_at) : "none"} sub="session" />
          </div>
          <div className="subwidget-stack">
            {SUBWIDGETS.map((item) => (
              <div className="subwidget" key={item.label}>
                <span>{item.label}</span>
                <strong className={item.tone}>{item.value}</strong>
                <em>{item.sub}</em>
              </div>
            ))}
          </div>
        </section>

        <section className="terminal-panel">
          <PanelHead title="News Flow" meta="filtered headlines" />
          <div className="news-flow">
            {NEWS.map(([time, ticker, title]) => (
              <div className="news-row" key={`${time}-${ticker}`}>
                <span>{time}</span>
                <strong>{ticker}</strong>
                <p>{title}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="terminal-panel">
          <PanelHead title="Options / Trade Flow" meta="unusual activity" />
          <table className="mini-table">
            <tbody>
              {FLOW.map(([symbol, side, premium, move]) => (
                <tr key={`${symbol}-${side}`}>
                  <td>{symbol}</td>
                  <td>{side}</td>
                  <td>{premium}</td>
                  <td className={move.startsWith("+") ? "pos" : "neg"}>{move}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="terminal-panel">
          <PanelHead title="Deployment Activity" meta={`${runCount} runs`} />
          {deployed.length === 0 && <div className="empty">No deployment activity yet.</div>}
          {deployed.map((run) => (
            <Link to={`/sessions/${run.id}`} className="terminal-list-row" key={run.id}>
              <div>
                <div className="terminal-row-title">{run.kind} · {shortId(run.strategy_id)}</div>
                <div className="page-sub">{shortId(run.id)} · {fmtTime(run.updated_at ?? run.created_at)}</div>
              </div>
              <span className={`badge ${stateClass(run.state)}`}>{run.state}</span>
            </Link>
          ))}
        </section>
      </div>
    </div>
  );
}

function PanelHead({ title, meta }: { title: string; meta: string }) {
  return (
    <div className="terminal-panel-head">
      <span>{title}</span>
      <em>{meta}</em>
    </div>
  );
}

function Mini({ label, value, sub }: { label: string; value: string | number; sub: string }) {
  return (
    <div className="mini">
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{sub}</em>
    </div>
  );
}

function chartPath(values: number[]) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * 600;
      const y = 188 - ((v - min) / (max - min || 1)) * 154;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}
