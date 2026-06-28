import type { TimelineNode, TimelineState } from "./timeline";
import type { TraceEvent } from "./types";

export type WorkflowStatus = "pending" | "ok" | "error" | "denied";
export type WorkflowKind = "prompt" | "tool" | "event";

export interface PromptMeta {
  prompt: string | null;
  title: string | null;
  actor?: TraceEvent["actor"];
  event?: TraceEvent;
}

export interface WorkflowItem {
  key: string;
  kind: WorkflowKind;
  name: string;
  status: WorkflowStatus;
  seq: number;
  ts: string;
  depth: number;
  span_id: string | null;
  parent_span_id: string | null;
  event?: TraceEvent;
  node?: TimelineNode;
  summary: string;
}

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function eventName(ev: TraceEvent): string {
  const data = rec(ev.data);
  if (ev.type === "strategy_proposed") return "strategy.proposed";
  if (ev.type === "run_transition") return `state.${str(data.to) ?? "transition"}`;
  if (ev.type === "run_progress") return `progress.${str(data.phase) ?? "update"}`;
  if (ev.type === "mark") return "market.mark";
  if (ev.type === "fill") return "model.fill";
  if (ev.type === "denial") return "denial";
  if (ev.type === "error") return "error";
  if (ev.type === "reasoning") return str(data.kind) ?? "reasoning";
  return ev.type;
}

function eventStatus(ev: TraceEvent): WorkflowStatus {
  if (ev.type === "error") return "error";
  if (ev.type === "denial") return "denied";
  return "ok";
}

function compact(value: unknown, max = 110): string {
  if (value == null) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function eventSummary(ev: TraceEvent): string {
  const data = rec(ev.data);
  switch (ev.type) {
    case "reasoning":
      return str(data.prompt) ?? str(data.text) ?? "";
    case "strategy_proposed":
      return str(data.name) ?? str(data.strategy_id) ?? "";
    case "run_transition":
      return `${str(data.from) ?? "-"} -> ${str(data.to) ?? "-"}`;
    case "run_progress": {
      const pct = typeof data.pct === "number" ? `${Math.round(data.pct)}% ` : "";
      return `${pct}${str(data.message) ?? str(data.phase) ?? ""}`;
    }
    case "denial":
      return str(data.reason) ?? compact(data);
    case "error":
      return str(data.message) ?? str(data.error) ?? compact(data);
    case "mark":
      return compact(data.marks ?? data);
    case "fill":
      return compact(data.deltas ?? data);
    default:
      return compact(data);
  }
}

function nodeSummary(node: TimelineNode): string {
  const callData = rec(node.call?.data);
  const args = callData.args ?? callData;
  const resultData = rec(node.result?.data);
  const warnings = resultData.warnings;
  const source = str(resultData.source) ?? str(rec(resultData.summary).source);
  const warningText = Array.isArray(warnings) && warnings.length ? `warnings ${warnings.join(", ")}` : "";
  return [compact(args), source ? `source ${source}` : "", warningText].filter(Boolean).join(" · ");
}

export function promptMeta(events: TraceEvent[] | undefined): PromptMeta {
  const list = events ?? [];
  for (const ev of list) {
    if (ev.type !== "session_open" && ev.type !== "reasoning") continue;
    const data = rec(ev.data);
    const prompt = str(data.prompt) ?? str(data.userPrompt);
    if (prompt) {
      return { prompt, title: str(data.title) ?? prompt.slice(0, 80), actor: ev.actor, event: ev };
    }
  }
  return { prompt: null, title: null };
}

export function buildWorkflowItems(state: TimelineState, events: TraceEvent[]): WorkflowItem[] {
  const sorted = events.slice().sort((a, b) => a.seq - b.seq);
  const meta = promptMeta(sorted);
  const openEvent = sorted.find((ev) => ev.type === "session_open");
  const rootSeq = meta.event?.seq ?? openEvent?.seq ?? -1;
  const rootTs = meta.event?.ts ?? openEvent?.ts ?? "";

  const items: WorkflowItem[] = [{
    key: "prompt",
    kind: "prompt",
    name: "user",
    status: state.closed ? "ok" : "pending",
    seq: rootSeq,
    ts: rootTs,
    depth: 0,
    span_id: null,
    parent_span_id: null,
    event: meta.event ?? openEvent,
    summary: meta.prompt ?? "Prompt not captured",
  }];

  const nodeBySeq = new Map<number, TimelineNode>();
  const spanDepth = new Map<string, number>();
  for (const node of state.nodes) nodeBySeq.set(node.seq, node);

  for (const ev of sorted) {
    if (ev.type === "tool_result" || ev.type === "session_open" || ev.type === "session_close" || ev.type === "keepalive") {
      continue;
    }

    if (ev.type === "tool_call") {
      const node = nodeBySeq.get(ev.seq);
      if (!node) continue;
      const parentDepth = node.parent_span_id ? spanDepth.get(node.parent_span_id) : undefined;
      const depth = parentDepth == null ? 1 : parentDepth + 1;
      if (node.span_id) spanDepth.set(node.span_id, depth);
      items.push({
        key: node.key,
        kind: "tool",
        name: node.name,
        status: node.status,
        seq: node.seq,
        ts: node.ts,
        depth,
        span_id: node.span_id,
        parent_span_id: node.parent_span_id,
        event: node.call,
        node,
        summary: nodeSummary(node),
      });
      continue;
    }

    const parentDepth = ev.parent_span_id ? spanDepth.get(ev.parent_span_id) : undefined;
    items.push({
      key: `${ev.type}-${ev.seq}`,
      kind: "event",
      name: eventName(ev),
      status: eventStatus(ev),
      seq: ev.seq,
      ts: ev.ts,
      depth: parentDepth == null ? 1 : parentDepth + 1,
      span_id: ev.span_id ?? null,
      parent_span_id: ev.parent_span_id ?? null,
      event: ev,
      summary: eventSummary(ev),
    });
  }

  return items;
}
