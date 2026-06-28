import type { TraceEvent } from "./types";

// Pure reducer: a run's append-only TraceEvent stream -> the three lanes the Runs view renders.
// No React, no I/O — fully unit-testable. The SSE hook and the replay scrubber both feed this.

export interface TimelineNode {
  // tool_call events keyed by span_id; the matching tool_result is folded in.
  key: string;
  seq: number;
  ts: string;
  span_id: string | null;
  parent_span_id: string | null;
  name: string; // tool name (from tool_call data.name) or event type
  status: "pending" | "ok" | "error" | "denied";
  call?: TraceEvent; // the tool_call event
  result?: TraceEvent; // the matching tool_result / error / denial event
  // panelType keys the static renderer registry; pulled from the result payload.
  panelType?: string;
  resultData?: unknown;
}

export interface ReasoningEntry {
  seq: number;
  ts: string;
  text: string;
}

export interface ProgressEntry {
  seq: number;
  ts: string;
  pct?: number;
  message?: string;
}

export interface TransitionEntry {
  seq: number;
  ts: string;
  from?: string;
  to?: string;
}

export interface TimelineState {
  // tool-call timeline (the spine), ordered by seq
  nodes: TimelineNode[];
  // reasoning rail (often empty for BYO agents)
  reasoning: ReasoningEntry[];
  // run lifecycle
  progress: ProgressEntry[];
  transitions: TransitionEntry[];
  // honest surfacing of refused / errored actions on the audited path
  denials: TraceEvent[];
  errors: TraceEvent[];
  // modeled marks/fills emitted by backtests or analysis workers
  marks: TraceEvent[];
  fills: TraceEvent[];
  // bookkeeping
  lastSeq: number;
  open: boolean;
  closed: boolean;
}

export function emptyTimeline(): TimelineState {
  return {
    nodes: [],
    reasoning: [],
    progress: [],
    transitions: [],
    denials: [],
    errors: [],
    marks: [],
    fills: [],
    lastSeq: -1,
    open: false,
    closed: false,
  };
}

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}
function num(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

// Find the open node a result should fold into: prefer span_id match, else most recent pending.
function indexForResult(nodes: TimelineNode[], ev: TraceEvent): number {
  const span = ev.span_id ?? null;
  if (span) {
    for (let i = nodes.length - 1; i >= 0; i--) {
      if (nodes[i].span_id === span) return i;
    }
  }
  for (let i = nodes.length - 1; i >= 0; i--) {
    if (nodes[i].status === "pending") return i;
  }
  return -1;
}

// Apply one event. Duplicate / out-of-order-by-seq events (seq <= lastSeq) are ignored,
// EXCEPT the very first event of a fresh state. This makes replay-from-seq idempotent.
export function applyEvent(state: TimelineState, ev: TraceEvent): TimelineState {
  if (ev.seq <= state.lastSeq && state.lastSeq !== -1) return state;

  const next: TimelineState = {
    ...state,
    nodes: state.nodes.slice(),
    reasoning: state.reasoning,
    progress: state.progress,
    transitions: state.transitions,
    denials: state.denials,
    errors: state.errors,
    marks: state.marks,
    fills: state.fills,
    lastSeq: Math.max(state.lastSeq, ev.seq),
  };

  const data = (ev.data ?? {}) as Record<string, unknown>;

  switch (ev.type) {
    case "keepalive":
      // Heartbeat only — advances lastSeq is wrong for keepalives in some servers, but our
      // contract gives keepalives a seq too; we simply do not render them.
      break;

    case "session_open":
      next.open = true;
      break;

    case "session_close":
      next.closed = true;
      break;

    case "reasoning": {
      const text = str(data.text) ?? str(data.message) ?? "";
      if (text) next.reasoning = [...state.reasoning, { seq: ev.seq, ts: ev.ts, text }];
      break;
    }

    case "tool_call": {
      next.nodes.push({
        key: ev.span_id ?? `seq-${ev.seq}`,
        seq: ev.seq,
        ts: ev.ts,
        span_id: ev.span_id ?? null,
        parent_span_id: ev.parent_span_id ?? null,
        name: str(data.name) ?? str(data.tool) ?? "tool",
        status: "pending",
        call: ev,
      });
      break;
    }

    case "tool_result": {
      const i = indexForResult(next.nodes, ev);
      const panelType =
        str(data.panelType) ??
        str((data.provenance as Record<string, unknown> | undefined)?.panelType) ??
        undefined;
      if (i >= 0) {
        next.nodes[i] = {
          ...next.nodes[i],
          status: "ok",
          result: ev,
          panelType,
          resultData: data.data ?? data.result ?? data,
        };
      } else {
        // Orphan result (no preceding call seen, e.g. replay started mid-stream).
        next.nodes.push({
          key: ev.span_id ?? `seq-${ev.seq}`,
          seq: ev.seq,
          ts: ev.ts,
          span_id: ev.span_id ?? null,
          parent_span_id: ev.parent_span_id ?? null,
          name: str(data.name) ?? "result",
          status: "ok",
          result: ev,
          panelType,
          resultData: data.data ?? data.result ?? data,
        });
      }
      break;
    }

    case "denial": {
      const i = indexForResult(next.nodes, ev);
      if (i >= 0) next.nodes[i] = { ...next.nodes[i], status: "denied", result: ev };
      next.denials = [...state.denials, ev];
      break;
    }

    case "error": {
      const i = indexForResult(next.nodes, ev);
      if (i >= 0) next.nodes[i] = { ...next.nodes[i], status: "error", result: ev };
      next.errors = [...state.errors, ev];
      break;
    }

    case "run_progress":
      next.progress = [
        ...state.progress,
        { seq: ev.seq, ts: ev.ts, pct: num(data.pct) ?? num(data.progress), message: str(data.message) },
      ];
      break;

    case "run_transition":
      next.transitions = [
        ...state.transitions,
        { seq: ev.seq, ts: ev.ts, from: str(data.from), to: str(data.to) },
      ];
      break;

    case "mark":
      next.marks = [...state.marks, ev];
      break;

    case "fill":
      next.fills = [...state.fills, ev];
      break;

    case "strategy_proposed":
      // Surfaced in lineage but not its own lane; treat as reasoning-adjacent note.
      next.reasoning = [
        ...state.reasoning,
        { seq: ev.seq, ts: ev.ts, text: `strategy proposed: ${str(data.name) ?? str(data.strategy_id) ?? ""}` },
      ];
      break;

    default:
      break;
  }

  return next;
}

// Fold an ordered list (e.g. the GET /events replay payload) into one state.
export function reduceEvents(events: TraceEvent[]): TimelineState {
  let s = emptyTimeline();
  for (const ev of events) s = applyEvent(s, ev);
  return s;
}

// For the replay scrubber: state as of (and including) a given seq.
export function reduceUpTo(events: TraceEvent[], maxSeq: number): TimelineState {
  let s = emptyTimeline();
  for (const ev of events) {
    if (ev.seq > maxSeq) break;
    s = applyEvent(s, ev);
  }
  return s;
}
