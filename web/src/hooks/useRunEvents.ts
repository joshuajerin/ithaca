import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { TraceEventSchema, type TraceEvent } from "../types";

export type ConnState = "connecting" | "open" | "closed" | "error";

// Subscribes to /api/runs/{id}/events via EventSource and accumulates the raw, ordered
// event list. The Runs page derives the three lanes from this list via the pure reducer,
// and the replay scrubber slices the same list — so live and replay share one source of truth.
//
// SSE replay: each connection uses a one-time ticket minted over authenticated REST. On a
// dropped connection we mint a fresh ticket and pass after_seq so replay resumes without gaps.
export function useRunEvents(runId: string | undefined): {
  events: TraceEvent[];
  conn: ConnState;
  error: string | null;
} {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [conn, setConn] = useState<ConnState>("connecting");
  const [error, setError] = useState<string | null>(null);
  const seenSeq = useRef<Set<number>>(new Set());
  const lastSeq = useRef<number>(-1);

  useEffect(() => {
    if (!runId) return;
    seenSeq.current = new Set();
    lastSeq.current = -1;
    setEvents([]);
    setError(null);
    setConn("connecting");

    let closed = false;
    let es: EventSource | null = null;
    let retryTimer: number | undefined;

    const connect = async () => {
      setConn("connecting");
      try {
        const ticket = await api.mintRunEventsTicket(runId, lastSeq.current);
        if (closed) return;
        es = new EventSource(api.eventsUrl(runId, {
          sseTicket: ticket.sse_ticket,
          afterSeq: lastSeq.current,
        }));

        es.onopen = () => {
          if (!closed) setConn("open");
        };
        es.onmessage = (e) => ingest(e.data);
        es.onerror = () => {
          if (closed) return;
          es?.close();
          es = null;
          setConn("error");
          retryTimer = window.setTimeout(connect, 1000);
        };
      } catch (err) {
        if (closed) return;
        setConn("error");
        setError(err instanceof Error ? err.message : "could not open event stream");
        retryTimer = window.setTimeout(connect, 3000);
      }
    };

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
      lastSeq.current = Math.max(lastSeq.current, tev.seq);
      setEvents((prev) => {
        const next = [...prev, tev];
        next.sort((a, b) => a.seq - b.seq);
        return next;
      });
    };

    void connect();

    return () => {
      closed = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      es?.close();
      setConn("closed");
    };
  }, [runId]);

  return { events, conn, error };
}
