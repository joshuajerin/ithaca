import type { Panel } from "@workspace/api-client-react";

export const GRID_COLUMNS = 12;

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Two grid rectangles overlap when they intersect on both axes. */
export function rectsOverlap(a: Rect, b: Rect): boolean {
  return (
    a.x < b.x + b.w &&
    a.x + a.w > b.x &&
    a.y < b.y + b.h &&
    a.y + a.h > b.y
  );
}

/** A rect fits when it is on-grid and clears every already-placed rect. */
function fits(rect: Rect, placed: Rect[]): boolean {
  if (rect.x < 0 || rect.y < 0 || rect.x + rect.w > GRID_COLUMNS) return false;
  return !placed.some((p) => rectsOverlap(rect, p));
}

/** First top-left slot (row-major scan) where a w×h rect fits among placed rects. */
function findSlot(w: number, h: number, placed: Rect[]): { x: number; y: number } {
  for (let y = 0; ; y++) {
    for (let x = 0; x + w <= GRID_COLUMNS; x++) {
      if (fits({ x, y, w, h }, placed)) return { x, y };
    }
  }
}

/** Clamp an AI-emitted layout to a sane on-grid rect (integer units, w within 1..12). */
function normalize(layout: Panel["layout"]): Rect {
  const w = Math.max(1, Math.min(GRID_COLUMNS, Math.round(layout.w) || 1));
  const h = Math.max(1, Math.round(layout.h) || 1);
  const x = Math.max(0, Math.round(layout.x) || 0);
  const y = Math.max(0, Math.round(layout.y) || 0);
  return { x, y, w, h };
}

/**
 * Resolve overlapping / off-grid panel layouts.
 *
 * Two passes, both in reading order (top-to-bottom, then left-to-right):
 *   1. Reserve every panel that is on-grid and does not collide with an
 *      already-reserved panel — these keep their AI-assigned positions.
 *   2. Reflow the remaining (conflicting / off-grid) panels into the first
 *      available slot, without disturbing the reserved ones.
 *
 * This guarantees non-conflicting panels are never displaced just because a
 * conflicting panel happened to be processed first. The returned array
 * preserves the original panel order and only allocates a new object for panels
 * whose layout actually changed.
 */
export function resolvePanelLayouts(panels: Panel[]): Panel[] {
  if (panels.length <= 1) return panels;

  const order = panels
    .map((panel, index) => ({ panel, index }))
    .sort((a, b) => {
      if (a.panel.layout.y !== b.panel.layout.y) return a.panel.layout.y - b.panel.layout.y;
      if (a.panel.layout.x !== b.panel.layout.x) return a.panel.layout.x - b.panel.layout.x;
      return a.index - b.index;
    });

  const placed: Rect[] = [];
  const resolved = new Map<string, Rect>();
  const needsReflow: { panel: Panel; rect: Rect }[] = [];

  // Pass 1 — reserve non-conflicting panels at their desired positions.
  for (const { panel } of order) {
    const desired = normalize(panel.layout);
    if (fits(desired, placed)) {
      placed.push(desired);
      resolved.set(panel.id, desired);
    } else {
      needsReflow.push({ panel, rect: desired });
    }
  }

  // Pass 2 — reflow conflicting panels into the gaps left behind.
  for (const { panel, rect } of needsReflow) {
    const slot = findSlot(rect.w, rect.h, placed);
    const final = { x: slot.x, y: slot.y, w: rect.w, h: rect.h };
    placed.push(final);
    resolved.set(panel.id, final);
  }

  return panels.map((panel) => {
    const r = resolved.get(panel.id)!;
    const l = panel.layout;
    if (r.x === l.x && r.y === l.y && r.w === l.w && r.h === l.h) return panel;
    return { ...panel, layout: { ...l, x: r.x, y: r.y, w: r.w, h: r.h } };
  });
}
