import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { TraceEventSchema, type TraceEvent } from "../types";

export type ConnState = "connecting" | "open" | "closed" | "error";

// Subscribes to /api/runs/{id}/events via EventSource and accumulates the raw, ordered
// event list. The Runs page derives the three lanes from this list via the pure reducer,
// and the replay scrubber slices the same list — so live and replay share one source of truth.
//
// SSE replay: the gateway honors Last-Event-ID (= seq) to resume. EventSource sends it
// automatically on reconnect, so on a dropped connection we resume from the last seq without gaps.
export function useRunEvents(runId: string | undefined): {
  events: TraceEvent[];
  conn: ConnState;
  error: string | null;
} {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [conn, setConn] = useState<ConnState>("connecting");
  const [error, setError] = useState<string | null>(null);
  const seenSeq = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!runId) return;
    seenSeq.current = new Set();
    setEvents([]);
    setError(null);
    setConn("connecting");

    const es = new EventSource(api.eventsUrl(runId));

    const ingest = (raw: string) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        return; // keepalive comment lines / malformed frames are ignored
      }
      const r = TraceEventSchema.safeParse(parsed);
      if (!r.success) return;
      const tev = r.data as TraceEvent;
      if (tev.type === "keepalive") return;
      if (seenSeq.current.has(tev.seq)) return;
      seenSeq.current.add(tev.seq);
      setEvents((prev) => {
        const next = [...prev, tev];
        next.sort((a, b) => a.seq - b.seq);
        return next;
      });
    };

    es.onopen = () => setConn("open");
    es.onmessage = (e) => ingest(e.data);
    es.onerror = () => {
      // EventSource auto-reconnects with Last-Event-ID; surface state but don't tear down.
      setConn((c) => (c === "open" ? "error" : c));
    };

    return () => {
      es.close();
      setConn("closed");
    };
  }, [runId]);

  return { events, conn, error };
}
