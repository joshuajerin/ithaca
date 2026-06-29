export function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

export function fmtTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtClock(ts: string | null | undefined): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour12: false });
}

export function stateClass(state: string | undefined): string {
  switch (state) {
    case "succeeded":
    case "done":
    case "live":
    case "promoted":
    case "approved":
    case "active":
    case "connected":
    case "filled":
      return "ok";
    case "failed":
    case "error":
    case "timeout":
    case "retired":
    case "denied":
    case "policy_denied":
    case "rejected":
      return "bad";
    case "running":
    case "queued":
    case "submitted":
    case "partially_filled":
      return "run";
    case "paused":
    case "pending":
    case "proposed":
    case "draft":
    case "approval_required":
    case "cancelled":
      return "warn";
    default:
      return "";
  }
}
