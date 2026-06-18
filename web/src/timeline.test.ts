import { describe, it, expect } from "vitest";
import { applyEvent, emptyTimeline, reduceEvents, reduceUpTo } from "./timeline";
import type { TraceEvent } from "./types";

const RUN = "11111111-1111-1111-1111-111111111111";
const TENANT = "00000000-0000-0000-0000-000000000001";

function ev(partial: Partial<TraceEvent> & { seq: number; type: TraceEvent["type"] }): TraceEvent {
  return {
    run_id: RUN,
    tenant_id: TENANT,
    ts: new Date(2026, 0, 1, 0, 0, partial.seq).toISOString(),
    data: {},
    ...partial,
  } as TraceEvent;
}

describe("timeline reducer", () => {
  it("folds a tool_call + matching tool_result into one node by span_id", () => {
    const events: TraceEvent[] = [
      ev({ seq: 0, type: "session_open" }),
      ev({ seq: 1, type: "tool_call", span_id: "s1", data: { name: "backtest.run" } }),
      ev({
        seq: 2,
        type: "tool_result",
        span_id: "s1",
        data: { panelType: "backtest", data: { stats: { sharpe: 1.2 } } },
      }),
      ev({ seq: 3, type: "session_close" }),
    ];
    const state = reduceEvents(events);
    expect(state.nodes).toHaveLength(1);
    expect(state.nodes[0].name).toBe("backtest.run");
    expect(state.nodes[0].status).toBe("ok");
    expect(state.nodes[0].panelType).toBe("backtest");
    expect(state.open).toBe(true);
    expect(state.closed).toBe(true);
    expect(state.lastSeq).toBe(3);
  });

  it("routes reasoning, progress, transitions, and denials into their own lanes", () => {
    const state = reduceEvents([
      ev({ seq: 0, type: "reasoning", data: { text: "thinking about momentum" } }),
      ev({ seq: 1, type: "run_progress", data: { pct: 50, message: "halfway" } }),
      ev({ seq: 2, type: "run_transition", data: { from: "running", to: "succeeded" } }),
      ev({ seq: 3, type: "tool_call", span_id: "s9", data: { name: "order.submit" } }),
      ev({ seq: 4, type: "denial", span_id: "s9", data: { reason: "risk gate" } }),
    ]);
    expect(state.reasoning).toHaveLength(1);
    expect(state.reasoning[0].text).toContain("momentum");
    expect(state.progress[0].pct).toBe(50);
    expect(state.transitions[0].to).toBe("succeeded");
    expect(state.denials).toHaveLength(1);
    // the node the denial belongs to is marked denied (audited-path honesty)
    expect(state.nodes[0].status).toBe("denied");
  });

  it("is idempotent for replay-from-seq (ignores seq <= lastSeq)", () => {
    let s = emptyTimeline();
    const e1 = ev({ seq: 5, type: "tool_call", span_id: "a", data: { name: "x" } });
    s = applyEvent(s, e1);
    // a duplicate of the same event must not double-append
    s = applyEvent(s, e1);
    // a stale earlier event must be dropped
    s = applyEvent(s, ev({ seq: 2, type: "tool_call", span_id: "b", data: { name: "y" } }));
    expect(s.nodes).toHaveLength(1);
    expect(s.lastSeq).toBe(5);
  });

  it("reduceUpTo reconstructs partial state for the replay scrubber", () => {
    const events: TraceEvent[] = [
      ev({ seq: 0, type: "tool_call", span_id: "s1", data: { name: "a" } }),
      ev({ seq: 1, type: "tool_result", span_id: "s1", data: { data: {} } }),
      ev({ seq: 2, type: "tool_call", span_id: "s2", data: { name: "b" } }),
    ];
    const mid = reduceUpTo(events, 1);
    expect(mid.nodes).toHaveLength(1);
    expect(mid.nodes[0].status).toBe("ok");
    const full = reduceUpTo(events, 2);
    expect(full.nodes).toHaveLength(2);
    expect(full.nodes[1].status).toBe("pending");
  });

  it("marks an errored tool node as error and records it", () => {
    const state = reduceEvents([
      ev({ seq: 0, type: "tool_call", span_id: "s1", data: { name: "market.get_ohlcv" } }),
      ev({ seq: 1, type: "error", span_id: "s1", data: { message: "boom" } }),
    ]);
    expect(state.nodes[0].status).toBe("error");
    expect(state.errors).toHaveLength(1);
  });
});
