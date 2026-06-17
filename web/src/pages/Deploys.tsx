import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks/useAsync";
import type { BacktestResult, RunRow } from "../types";
import { EquityCurve } from "../panels/EquityCurve";
import { RiskBadge } from "../panels/RiskBadge";
import { fmtTime, shortId, stateClass } from "../lib/format";

type Tab = "backtest" | "paper";

export function Deploys() {
  const [tab, setTab] = useState<Tab>("backtest");
  const { data, loading, error } = useAsync<RunRow[]>((s) => api.listRuns(tab, s), [tab]);
  const navigate = useNavigate();

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="page-title">Deploys</div>
          <div className="page-sub">equity curve · stats · risk badge</div>
        </div>
      </div>

      <div className="tabs">
        <div className={`tab ${tab === "backtest" ? "active" : ""}`} onClick={() => setTab("backtest")}>
          Backtests
        </div>
        <div className={`tab ${tab === "paper" ? "active" : ""}`} onClick={() => setTab("paper")}>
          Paper
        </div>
      </div>

      {error && <div className="banner">Failed to load: {error}</div>}
      {loading && <div className="empty">Loading {tab} runs…</div>}
      {!loading && !error && (data?.length ?? 0) === 0 && <div className="empty">No {tab} deploys.</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {(data ?? []).map((r) => (
          <DeployCard key={r.id} run={r} onOpen={() => navigate(`/runs/${r.id}`)} />
        ))}
      </div>
    </div>
  );
}

function DeployCard({ run, onOpen }: { run: RunRow; onOpen: () => void }) {
  const result = (run.result ?? {}) as Partial<BacktestResult> & { data?: Partial<BacktestResult> };
  // The result row may wrap the backtest data in a provenance envelope.
  const bt: Partial<BacktestResult> = (result.data ?? result) as Partial<BacktestResult>;
  const curve = Array.isArray(bt.equityCurve) ? bt.equityCurve : [];
  const stats = bt.stats ?? {};

  return (
    <div style={{ border: "1px solid var(--border)", padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
        <div className="mono" style={{ fontSize: 12 }}>
          <a onClick={onOpen} style={{ cursor: "pointer" }}>
            {shortId(run.id)}
          </a>{" "}
          <span className={`badge ${stateClass(run.state)}`}>{run.state}</span>{" "}
          <span style={{ color: "var(--muted-dim)" }}>strategy {shortId(run.strategy_id)}</span>
        </div>
        <span className="page-sub">{fmtTime(run.created_at)}</span>
      </div>

      {curve.length > 1 ? (
        <>
          <EquityCurve points={curve} height={140} />
          <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
            {Object.entries(stats)
              .filter(([, v]) => typeof v === "number")
              .slice(0, 5)
              .map(([k, v]) => (
                <span className="kv" key={k}>
                  <span className="k">{k}</span> {(v as number).toFixed(2)}
                </span>
              ))}
          </div>
          <div style={{ marginTop: 8 }}>
            <RiskBadge risk={bt.risk} relaxed={bt.relaxed} />
          </div>
        </>
      ) : (
        <div className="empty">No result artifact yet — open the run to watch it stream.</div>
      )}
    </div>
  );
}
