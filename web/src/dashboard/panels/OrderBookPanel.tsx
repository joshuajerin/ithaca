// @ts-nocheck
// Light-theme copy of web/src/components/terminal/panels/OrderBookPanel.tsx
// DO NOT edit the original at web/src/components/terminal/panels/.
// Note: Replay slider removed in this light copy to avoid shadcn/Radix dependency; static book only.
import React from "react";

export function OrderBookPanel({ data }: { data: any }) {
  const frame = data;
  const currentTime: string | undefined = frame?.time ?? data.timestamp;
  const replayReal = data.replayReal === true;
  const coverage: string | undefined = data.coverage;

  return (
    <div className="panel-light" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>{data.symbol} · Order Book</div>
          <div style={{ fontSize: 20, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--fg)" }}>${frame.lastPrice.toFixed(2)}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.14em" }}>Spread</div>
          <div style={{ fontSize: 13, fontFamily: "var(--font-mono)", color: "var(--fg)" }}>${frame.spread.toFixed(2)}</div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 10, flexShrink: 0 }}>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px",
          fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em",
          borderRadius: "var(--radius-sm)",
          background: replayReal ? "rgba(47,143,73,0.1)" : "rgba(201,121,26,0.1)",
          color: replayReal ? "var(--pos)" : "var(--warn)",
          border: `1px solid ${replayReal ? "rgba(47,143,73,0.3)" : "rgba(201,121,26,0.3)"}`,
        }}>
          <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: replayReal ? "var(--pos)" : "var(--warn)" }} />
          {replayReal ? "Real" : "Simulated"}
        </span>
        <span style={{ color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {replayReal ? "IEX DEEP · venue-only · T+1" : coverage || "Simulated depth"}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, flex: 1, minHeight: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted)", marginBottom: 4, flexShrink: 0 }}>Bids</div>
          <div style={{ flex: 1, minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column", gap: 2 }}>
            {frame.bids.map((level: any, i: any) => (
              <div key={i} style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "3px 6px", fontSize: 11, fontFamily: "var(--font-mono)", overflow: "hidden" }}>
                <div style={{ position: "absolute", inset: 0, background: "rgba(47,143,73,0.08)", width: `${level.depth * 100}%` }} />
                <span style={{ position: "relative", fontWeight: 700, color: "var(--pos)" }}>${level.price.toFixed(2)}</span>
                <span style={{ position: "relative", color: "var(--muted)" }}>{level.size.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted)", marginBottom: 4, flexShrink: 0 }}>Asks</div>
          <div style={{ flex: 1, minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column", gap: 2 }}>
            {frame.asks.map((level: any, i: any) => (
              <div key={i} style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "3px 6px", fontSize: 11, fontFamily: "var(--font-mono)", overflow: "hidden" }}>
                <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, background: "rgba(182,66,53,0.07)", width: `${level.depth * 100}%` }} />
                <span style={{ position: "relative", color: "var(--muted)" }}>${level.price.toFixed(2)}</span>
                <span style={{ position: "relative", color: "var(--neg)", opacity: 0.8 }}>{level.size.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ flexShrink: 0, borderTop: "1px solid var(--border-soft)", paddingTop: 8 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--muted)" }}>Recent Tape</div>
          {currentTime && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{currentTime}</span>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 90, overflow: "auto" }}>
          {frame.tape.map((print: any, i: any) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              fontSize: 10, fontFamily: "var(--font-mono)", gap: 8, padding: "1px 4px",
              borderRadius: 3,
              background: print.isBlock ? "rgba(201,121,26,0.08)" : print.isSweep ? "rgba(47,107,229,0.08)" : "transparent",
            }}>
              <span style={{ color: "var(--muted)", width: 56, flexShrink: 0 }}>{print.time}</span>
              <span style={{ fontWeight: 700, width: 56, flexShrink: 0, color: print.side === "buy" ? "var(--pos)" : "var(--neg)" }}>${print.price.toFixed(2)}</span>
              <span style={{ color: "var(--muted)", width: 56, flexShrink: 0, textAlign: "right" }}>{print.size.toLocaleString()}</span>
              <span style={{ width: 40, flexShrink: 0, textAlign: "right", fontSize: 8.5, textTransform: "uppercase", letterSpacing: "0.08em",
                color: print.isBlock ? "var(--warn)" : print.isSweep ? "var(--info)" : "var(--muted-dim)" }}>
                {print.isBlock ? "block" : print.isSweep ? "sweep" : print.side}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
