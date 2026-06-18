import React, { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BellRing, X } from "lucide-react";

interface AlertEvent {
  id: string;
  symbol: string;
  metricLabel: string;
  message: string;
  at?: string;
}

interface AlertsNotificationsProps {
  sessionId?: string;
  onNew?: (event: AlertEvent) => void;
}

/**
 * Polls the session's fired trade-flow alerts and renders them as a notification
 * feed in the terminal sidebar. Newly-seen events are reported via onNew so the
 * shell can also surface a toast.
 */
export function AlertsNotifications({ sessionId, onNew }: AlertsNotificationsProps) {
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const seenIds = useRef<Set<string>>(new Set());
  const onNewRef = useRef(onNew);
  useEffect(() => {
    onNewRef.current = onNew;
  });

  // Reset the seen-set whenever the session changes so a fresh session starts clean.
  useEffect(() => {
    seenIds.current = new Set();
    setEvents([]);
  }, [sessionId]);

  const poll = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await fetch(`/api/alerts/events?sessionId=${encodeURIComponent(sessionId)}`);
      if (!res.ok) return;
      const json = await res.json();
      const incoming: AlertEvent[] = json.events ?? [];
      const fresh = incoming.filter((e) => !seenIds.current.has(e.id));
      if (fresh.length) {
        fresh.forEach((e) => {
          seenIds.current.add(e.id);
          onNewRef.current?.(e);
        });
      }
      setEvents(incoming);
    } catch {
      /* transient */
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    poll();
    const id = window.setInterval(poll, 4000);
    return () => window.clearInterval(id);
  }, [sessionId, poll]);

  const handleClear = async () => {
    if (!sessionId) return;
    try {
      await fetch(`/api/alerts/events?sessionId=${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
      });
      setEvents([]);
    } catch {
      /* ignore */
    }
  };

  if (!sessionId || events.length === 0) return null;

  return (
    <div className="shrink-0 border-b border-border bg-[#0a0a0a]">
      <div className="px-5 pt-3 pb-2 flex items-center justify-between">
        <span className="editorial-label text-[9px] text-amber-400 flex items-center gap-1.5">
          <BellRing className="w-3 h-3" strokeWidth={1.5} />
          Alerts · {events.length}
        </span>
        <button
          onClick={handleClear}
          className="text-muted-foreground hover:text-white transition-colors flex items-center gap-1 editorial-label text-[8.5px]"
        >
          <X className="w-3 h-3" strokeWidth={1.5} />
          Clear
        </button>
      </div>
      <div className="px-5 pb-3 max-h-44 overflow-y-auto scrollbar-none flex flex-col gap-1.5">
        <AnimatePresence initial={false}>
          {events.slice(0, 12).map((ev) => (
            <motion.div
              key={ev.id}
              initial={{ opacity: 0, x: 8, filter: "blur(2px)" }}
              animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              className="border-l-2 border-amber-400/70 pl-2.5 py-1"
            >
              <p className="font-serif text-[13px] leading-snug text-gray-100">{ev.message}</p>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
