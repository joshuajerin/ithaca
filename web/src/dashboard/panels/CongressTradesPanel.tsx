// @ts-nocheck
// Light-theme copy of web/src/components/terminal/panels/CongressTradesPanel.tsx
// DO NOT edit the original at web/src/components/terminal/panels/.
import React, { useMemo, useState } from "react";

interface CongressTrade {
  id: string;
  member: string;
  chamber?: string | null;
  party?: string | null;
  partyCode?: string | null;
  ticker?: string | null;
  type: string;
  amountRange?: string | null;
  transactionDate?: string | null;
  disclosureDate?: string | null;
  lagDays?: number | null;
  sourceUrl?: string | null;
}

interface CongressHighlight {
  kind: string;
  label: string;
  detail: string;
  ticker?: string | null;
}

interface CongressStats {
  total: number;
  buys: number;
  sells: number;
  exchanges: number;
  uniqueMembers: number;
}

interface CongressTradesData {
  scope: string;
  ticker?: string | null;
  trades: CongressTrade[];
  highlights: CongressHighlight[];
  stats: CongressStats;
  lagNote: string;
  disclaimer: string;
  asOf?: string | null;
  source?: string | null;
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });
}

function partyStyle(code?: string | null, party?: string | null) {
  const p = (code || party || "").toLowerCase();
  if (p === "d" || p === "democrat") return { color: "var(--info)", borderColor: "rgba(47,107,229,0.3)", background: "rgba(47,107,229,0.07)" };
  if (p === "r" || p === "republican") return { color: "var(--neg)", borderColor: "rgba(182,66,53,0.3)", background: "rgba(182,66,53,0.07)" };
  return { color: "var(--muted)", borderColor: "var(--border-soft)", background: "transparent" };
}

type SideFilter = "all" | "buy" | "sell";

export function CongressTradesPanel({ data }: { data: CongressTradesData }) {
  const [side, setSide] = useState<SideFilter>("all");
  const isMock = data.source === "mock";

  const trades = useMemo(
    () => (side === "all" ? data.trades : data.trades.filter(t => t.type === side)),
    [data.trades, side],
  );

  const s = data.stats;

  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", color: "var(--fg)" }}>Congress · {data.scope}</span>
        </div>
        <span style={{ fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em", display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: isMock ? "var(--muted)" : "var(--pos)", display: "inline-block" }} />
          {isMock ? "sample" : "live"}
        </span>
      </div>

      {/* Stats strip */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 6, marginBottom: 10, flexShrink: 0, textAlign: "center" }}>
        <div style={{ border: "1px solid var(--border-soft)", padding: "6px 4px", borderRadius: "var(--radius-sm)" }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--fg)" }}>{s.total}</div>
          <div style={{ fontSize: 8.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Trades</div>
        </div>
        <div style={{ border: "1px solid rgba(47,143,73,0.25)", padding: "6px 4px", borderRadius: "var(--radius-sm)", background: "rgba(47,143,73,0.06)" }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--pos)" }}>{s.buys}</div>
          <div style={{ fontSize: 8.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Buys</div>
        </div>
        <div style={{ border: "1px solid rgba(182,66,53,0.25)", padding: "6px 4px", borderRadius: "var(--radius-sm)", background: "rgba(182,66,53,0.06)" }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--neg)" }}>{s.sells}</div>
          <div style={{ fontSize: 8.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Sells</div>
        </div>
        <div style={{ border: "1px solid var(--border-soft)", padding: "6px 4px", borderRadius: "var(--radius-sm)" }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--fg)" }}>{s.uniqueMembers}</div>
          <div style={{ fontSize: 8.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em" }}>Members</div>
        </div>
      </div>

      {/* Highlights */}
      {data.highlights.length > 0 && (
        <div style={{ marginBottom: 8, flexShrink: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          {data.highlights.slice(0, 2).map((h, i) => {
            const cluster = h.kind === "cluster_buy";
            const sale = h.kind === "large_sale";
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 8px", borderRadius: "var(--radius-sm)",
                border: `1px solid ${cluster ? "rgba(201,121,26,0.35)" : sale ? "rgba(182,66,53,0.25)" : "rgba(47,143,73,0.25)"}`,
                background: cluster ? "rgba(201,121,26,0.07)" : sale ? "rgba(182,66,53,0.05)" : "rgba(47,143,73,0.05)" }}>
                <span style={{ fontSize: 10, color: "var(--fg)" }}>
                  <strong style={{ color: cluster ? "var(--warn)" : sale ? "var(--neg)" : "var(--pos)" }}>{h.label}</strong>
                  <span style={{ color: "var(--muted)" }}> — {h.detail}</span>
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Lag note */}
      <div style={{ marginBottom: 8, flexShrink: 0, display: "flex", alignItems: "flex-start", gap: 6, fontSize: 9, color: "var(--muted)", border: "1px solid var(--border-soft)", padding: "5px 8px", borderRadius: "var(--radius-sm)" }}>
        <span>⏱</span>
        <span style={{ lineHeight: 1.5 }}>{data.lagNote}</span>
      </div>

      {/* Filter tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 8, flexShrink: 0 }}>
        {(["all", "buy", "sell"] as const).map(t => (
          <button key={t} onClick={() => setSide(t)} style={{
            fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", padding: "3px 10px",
            border: `1px solid ${side === t ? "var(--fg)" : "var(--border-soft)"}`,
            background: side === t ? "var(--fg)" : "transparent",
            color: side === t ? "var(--surface)" : "var(--muted)",
            cursor: "pointer", borderRadius: "var(--radius-sm)",
            fontFamily: "var(--font-sans)",
          }}>
            {t === "all" ? "All" : t === "buy" ? "Buys" : "Sells"}
          </button>
        ))}
      </div>

      {/* Column header */}
      <div style={{ display: "grid", gridTemplateColumns: "1.5fr 0.6fr 0.55fr 1fr 1.25fr", gap: 8, padding: "0 8px 6px", fontSize: 9, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.1em", borderBottom: "1px solid var(--border-soft)", flexShrink: 0 }}>
        <span>Member</span><span>Ticker</span><span style={{ textAlign: "center" }}>Side</span><span style={{ textAlign: "right" }}>Amount</span><span style={{ textAlign: "right" }}>Traded → Disclosed</span>
      </div>

      {/* Rows */}
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        {trades.length === 0 && (
          <div style={{ fontSize: 11, color: "var(--muted)", padding: "12px 8px" }}>No disclosed trades match this filter.</div>
        )}
        {trades.map(t => {
          const buy = t.type === "buy";
          const sell = t.type === "sell";
          const ps = partyStyle(t.partyCode, t.party);
          return (
            <div key={t.id} style={{ display: "grid", gridTemplateColumns: "1.5fr 0.6fr 0.55fr 1fr 1.25fr", gap: 8, alignItems: "center", padding: "7px 8px", borderBottom: "1px solid var(--border-soft)" }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--fg)" }}>{t.member}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
                  <span style={{ fontSize: 8.5, padding: "1px 5px", border: `1px solid ${ps.borderColor}`, background: ps.background, color: ps.color, textTransform: "uppercase", borderRadius: 3 }}>{t.partyCode || (t.party ? t.party[0] : "?")}</span>
                  <span style={{ fontSize: 9, color: "var(--muted)" }}>{t.chamber || "—"}</span>
                </div>
              </div>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", overflow: "hidden", textOverflow: "ellipsis", color: "var(--fg)" }}>{t.ticker || "—"}</div>
              <div style={{ display: "flex", justifyContent: "center" }}>
                {buy ? (
                  <span style={{ fontSize: 9, color: "var(--pos)", border: "1px solid rgba(47,143,73,0.3)", background: "rgba(47,143,73,0.07)", padding: "2px 6px", textTransform: "uppercase", borderRadius: 3 }}>↑ Buy</span>
                ) : sell ? (
                  <span style={{ fontSize: 9, color: "var(--neg)", border: "1px solid rgba(182,66,53,0.3)", background: "rgba(182,66,53,0.07)", padding: "2px 6px", textTransform: "uppercase", borderRadius: 3 }}>↓ Sell</span>
                ) : (
                  <span style={{ fontSize: 9, color: "var(--muted)", border: "1px solid var(--border-soft)", padding: "2px 6px", textTransform: "uppercase", borderRadius: 3 }}>⇄ Exch</span>
                )}
              </div>
              <div style={{ textAlign: "right", fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--fg)", overflow: "hidden", textOverflow: "ellipsis" }}>{t.amountRange || "—"}</div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--fg)" }}>{fmtDate(t.transactionDate)}</div>
                <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--muted)" }}>disc {fmtDate(t.disclosureDate)}{t.lagDays != null ? ` · ${t.lagDays}d` : ""}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{ flexShrink: 0, marginTop: 6, display: "flex", alignItems: "flex-start", gap: 6, fontSize: 9, color: "var(--muted)", borderTop: "1px solid var(--border-soft)", paddingTop: 6 }}>
        <span>ⓘ</span>
        <span style={{ lineHeight: 1.5 }}>{data.disclaimer}</span>
      </div>
    </div>
  );
}
