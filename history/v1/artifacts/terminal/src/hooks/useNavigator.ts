import { useCallback, useEffect, useRef, useState } from "react";
import type { NavigationStop, NavigationTour } from "@workspace/api-client-react";

export interface NavigatorPoint {
  x: number;
  y: number;
}

export type NavigatorStatus = "idle" | "moving" | "reading";

interface UseNavigatorArgs {
  /** Highlight a panel by id (or clear with null) while the cursor rests on it. */
  onHighlight: (panelId: string | null) => void;
  /** Fired when a tour finishes naturally (not when stopped by the user). */
  onComplete?: () => void;
}

interface UseNavigator {
  active: boolean;
  status: NavigatorStatus;
  /** Current cursor target in viewport coordinates, or null when idle. */
  point: NavigatorPoint | null;
  caption: string;
  title: string;
  /** 1-based index of the current stop. */
  index: number;
  total: number;
  /**
   * Begin running a tour. A tour with no resolvable stops is a no-op.
   * Pass `{ narrated: true }` to suppress the built-in dwell auto-advance — the
   * cursor then only moves when an external driver (e.g. the voice conductor)
   * calls `goTo`, keeping each stop on screen for as long as it is being spoken.
   */
  start: (tour: NavigationTour, opts?: { narrated?: boolean }) => void;
  /**
   * Move the cursor to the stop at `index` and resolve once it has landed (the
   * caption is shown and the panel highlighted). Used to sync cursor movement to
   * spoken narration. Resolves immediately if the tour is no longer active.
   */
  goTo: (index: number) => Promise<void>;
  stop: () => void;
  next: () => void;
  prev: () => void;
}

/** Look up the on-screen element for a panel id. */
function findPanelEl(panelId: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-panel-id="${CSS.escape(panelId)}"]`);
}

/** Centre of an element in viewport coordinates (matches position: fixed). */
function centerOf(el: HTMLElement): NavigatorPoint {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

/** Dwell time scaled to caption length, clamped to a comfortable range. */
function dwellFor(caption: string): number {
  const words = caption.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(3200, Math.min(7000, words * 360 + 1600));
}

export function useNavigator(args: UseNavigatorArgs): UseNavigator {
  const { onHighlight, onComplete } = args;

  const [active, setActive] = useState(false);
  const [status, setStatus] = useState<NavigatorStatus>("idle");
  const [point, setPoint] = useState<NavigatorPoint | null>(null);
  const [caption, setCaption] = useState("");
  const [title, setTitle] = useState("");
  const [index, setIndex] = useState(0);
  const [total, setTotal] = useState(0);

  const highlightRef = useRef(onHighlight);
  const completeRef = useRef(onComplete);
  useEffect(() => {
    highlightRef.current = onHighlight;
    completeRef.current = onComplete;
  });

  const stopsRef = useRef<NavigationStop[]>([]);
  const indexRef = useRef(0);
  const activeRef = useRef(false);
  // Narrated mode: an external driver (the voice conductor) advances the cursor
  // in step with spoken narration, so the built-in dwell auto-advance is off.
  const narratedRef = useRef(false);
  // The panel id the cursor is currently resting on — used to re-measure on resize.
  const currentPanelRef = useRef<string | null>(null);

  const dwellTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const moveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (dwellTimer.current) {
      clearTimeout(dwellTimer.current);
      dwellTimer.current = null;
    }
    if (moveTimer.current) {
      clearTimeout(moveTimer.current);
      moveTimer.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    clearTimers();
    activeRef.current = false;
    currentPanelRef.current = null;
    stopsRef.current = [];
    indexRef.current = 0;
    highlightRef.current(null);
    setActive(false);
    setStatus("idle");
    setPoint(null);
    setCaption("");
    setTitle("");
    setIndex(0);
    setTotal(0);
  }, [clearTimers]);

  // Forward declaration so goTo can schedule the next hop.
  const goToRef = useRef<(i: number) => Promise<void>>(async () => {});

  const goTo = useCallback((i: number): Promise<void> => {
    return new Promise<void>((resolve) => {
      if (!activeRef.current) return resolve();
      clearTimers();
      const stops = stopsRef.current;
      if (i < 0) i = 0;
      if (i >= stops.length) {
        // Reached the end. In narrated mode the driver owns completion (it stops
        // the tour once the last caption finishes), so just resolve. Otherwise
        // hold the final caption briefly, then dismiss.
        if (narratedRef.current) return resolve();
        const finish = () => {
          if (!activeRef.current) return;
          const done = completeRef.current;
          stop();
          done?.();
        };
        dwellTimer.current = setTimeout(finish, 1200);
        return resolve();
      }

      const stop_ = stops[i];
      const el = findPanelEl(stop_.panelId);
      if (!el) {
        // Panel not in the DOM (e.g. removed) — skip to the next stop.
        indexRef.current = i;
        goToRef.current(i + 1).then(resolve);
        return;
      }

      indexRef.current = i;
      currentPanelRef.current = stop_.panelId;
      setIndex(i + 1);
      setStatus("moving");

      // Bring the panel into view, then measure once the scroll settles so the
      // cursor lands on its real on-screen position.
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      moveTimer.current = setTimeout(() => {
        if (!activeRef.current) return resolve();
        const target = findPanelEl(stop_.panelId);
        if (target) setPoint(centerOf(target));
        setCaption(stop_.caption);
        highlightRef.current(stop_.panelId);
        setStatus("reading");
        // Auto-advance after the dwell, unless an external driver is narrating
        // (narrated mode) — then the cursor only advances when goTo is called
        // again, keeping it on the panel for as long as the caption is spoken.
        if (!narratedRef.current) {
          dwellTimer.current = setTimeout(() => {
            goToRef.current(indexRef.current + 1);
          }, dwellFor(stop_.caption));
        }
        resolve();
      }, 480);
    });
  }, [clearTimers, stop]);

  useEffect(() => {
    goToRef.current = goTo;
  }, [goTo]);

  const start = useCallback((tour: NavigationTour, opts?: { narrated?: boolean }) => {
    clearTimers();
    const stops = (tour.stops || []).filter((s) => s && s.panelId && s.caption);
    if (stops.length === 0) return;
    stopsRef.current = stops;
    indexRef.current = 0;
    activeRef.current = true;
    narratedRef.current = !!opts?.narrated;
    currentPanelRef.current = null;
    setActive(true);
    setTitle(tour.title || "Guided walkthrough");
    setTotal(stops.length);
    setStatus("moving");
    setPoint(null);
    setCaption("");
    // In narrated mode the driver kicks off the first hop (and every advance) in
    // step with the spoken captions; in auto mode we start straight away.
    if (!narratedRef.current) goTo(0);
  }, [clearTimers, goTo]);

  const next = useCallback(() => {
    if (!activeRef.current) return;
    goTo(indexRef.current + 1);
  }, [goTo]);

  const prev = useCallback(() => {
    if (!activeRef.current) return;
    goTo(indexRef.current - 1);
  }, [goTo]);

  // Keep the cursor pinned to its panel while the user scrolls or resizes.
  useEffect(() => {
    if (!active) return;
    const remeasure = () => {
      const pid = currentPanelRef.current;
      if (!pid) return;
      const el = findPanelEl(pid);
      if (el) setPoint(centerOf(el));
    };
    window.addEventListener("resize", remeasure);
    return () => window.removeEventListener("resize", remeasure);
  }, [active]);

  // Cleanup on unmount.
  useEffect(() => () => clearTimers(), [clearTimers]);

  return {
    active,
    status,
    point,
    caption,
    title,
    index,
    total,
    start,
    goTo,
    stop,
    next,
    prev,
  };
}
