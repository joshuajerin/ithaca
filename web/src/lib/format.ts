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
    case "live":
    case "promoted":
      return "ok";
    case "failed":
    case "timeout":
    case "retired":
      return "bad";
    case "running":
    case "queued":
      return "run";
    case "paused":
      return "warn";
    default:
      return "";
  }
}
