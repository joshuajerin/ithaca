import { describe, it, expect } from "vitest";
import type { Panel } from "@workspace/api-client-react";
import { GRID_COLUMNS, rectsOverlap, resolvePanelLayouts, type Rect } from "./layout";

/** Build a minimal valid Panel with the given id and layout. */
function makePanel(id: string, layout: { x: number; y: number; w: number; h: number }): Panel {
  return {
    id,
    type: "price_chart",
    title: id,
    layout,
    status: "ok",
  };
}

/** Derive the on-grid Rect a resolved panel ended up at. */
function rectOf(panel: Panel): Rect {
  return { x: panel.layout.x, y: panel.layout.y, w: panel.layout.w, h: panel.layout.h };
}

/** Assert no two rects in the list overlap. */
function expectNoOverlaps(panels: Panel[]): void {
  for (let i = 0; i < panels.length; i++) {
    for (let j = i + 1; j < panels.length; j++) {
      const a = rectOf(panels[i]);
      const b = rectOf(panels[j]);
      expect(
        rectsOverlap(a, b),
        `panels "${panels[i].id}" and "${panels[j].id}" overlap`,
      ).toBe(false);
    }
  }
}

/** Assert every rect is on-grid (non-negative, within GRID_COLUMNS, integer units). */
function expectOnGrid(panels: Panel[]): void {
  for (const panel of panels) {
    const r = rectOf(panel);
    expect(Number.isInteger(r.x)).toBe(true);
    expect(Number.isInteger(r.y)).toBe(true);
    expect(Number.isInteger(r.w)).toBe(true);
    expect(Number.isInteger(r.h)).toBe(true);
    expect(r.x).toBeGreaterThanOrEqual(0);
    expect(r.y).toBeGreaterThanOrEqual(0);
    expect(r.w).toBeGreaterThanOrEqual(1);
    expect(r.x + r.w).toBeLessThanOrEqual(GRID_COLUMNS);
  }
}

/** Look up a resolved panel by id. */
function byId(panels: Panel[], id: string): Panel {
  const found = panels.find((p) => p.id === id);
  if (!found) throw new Error(`panel "${id}" not found in resolved output`);
  return found;
}

describe("rectsOverlap", () => {
  it("detects overlapping rects", () => {
    expect(rectsOverlap({ x: 0, y: 0, w: 4, h: 4 }, { x: 2, y: 2, w: 4, h: 4 })).toBe(true);
  });

  it("treats edge-adjacent rects as non-overlapping", () => {
    expect(rectsOverlap({ x: 0, y: 0, w: 4, h: 4 }, { x: 4, y: 0, w: 4, h: 4 })).toBe(false);
    expect(rectsOverlap({ x: 0, y: 0, w: 4, h: 4 }, { x: 0, y: 4, w: 4, h: 4 })).toBe(false);
  });

  it("treats fully separate rects as non-overlapping", () => {
    expect(rectsOverlap({ x: 0, y: 0, w: 2, h: 2 }, { x: 6, y: 6, w: 2, h: 2 })).toBe(false);
  });
});

describe("resolvePanelLayouts", () => {
  it("returns the input unchanged when there is 0 or 1 panel", () => {
    const empty: Panel[] = [];
    expect(resolvePanelLayouts(empty)).toBe(empty);

    const single = [makePanel("a", { x: 3, y: 1, w: 4, h: 2 })];
    const resolvedSingle = resolvePanelLayouts(single);
    expect(resolvedSingle).toBe(single);
  });

  it("preserves an already-clean layout by identity (same object references)", () => {
    const panels = [
      makePanel("a", { x: 0, y: 0, w: 6, h: 4 }),
      makePanel("b", { x: 6, y: 0, w: 6, h: 4 }),
      makePanel("c", { x: 0, y: 4, w: 12, h: 3 }),
    ];

    const resolved = resolvePanelLayouts(panels);

    expect(resolved).toHaveLength(panels.length);
    resolved.forEach((panel, i) => {
      // No layout changed, so each panel keeps its original object reference.
      expect(panel).toBe(panels[i]);
    });
    expectNoOverlaps(resolved);
    expectOnGrid(resolved);
  });

  it("preserves the original panel order in the output", () => {
    const panels = [
      makePanel("first", { x: 0, y: 6, w: 6, h: 3 }),
      makePanel("second", { x: 0, y: 0, w: 6, h: 3 }),
      makePanel("third", { x: 6, y: 0, w: 6, h: 3 }),
    ];

    const resolved = resolvePanelLayouts(panels);

    expect(resolved.map((p) => p.id)).toEqual(["first", "second", "third"]);
  });

  it("reflows fully stacked panels into a non-overlapping layout", () => {
    // All four panels claim the exact same slot.
    const panels = [
      makePanel("a", { x: 0, y: 0, w: 6, h: 4 }),
      makePanel("b", { x: 0, y: 0, w: 6, h: 4 }),
      makePanel("c", { x: 0, y: 0, w: 6, h: 4 }),
      makePanel("d", { x: 0, y: 0, w: 6, h: 4 }),
    ];

    const resolved = resolvePanelLayouts(panels);

    expect(resolved).toHaveLength(4);
    expectNoOverlaps(resolved);
    expectOnGrid(resolved);
  });

  it("keeps non-conflicting panels in place and only moves the colliding one", () => {
    // "clean" panels occupy the top row; "intruder" overlaps "left".
    const left = makePanel("left", { x: 0, y: 0, w: 6, h: 4 });
    const right = makePanel("right", { x: 6, y: 0, w: 6, h: 4 });
    const intruder = makePanel("intruder", { x: 2, y: 1, w: 6, h: 4 });

    const resolved = resolvePanelLayouts([left, right, intruder]);

    // The clean panels keep their AI-assigned positions (same object refs).
    expect(byId(resolved, "left")).toBe(left);
    expect(byId(resolved, "right")).toBe(right);

    // The intruder was relocated off the clean panels.
    const movedIntruder = byId(resolved, "intruder");
    expect(movedIntruder).not.toBe(intruder);

    expectNoOverlaps(resolved);
    expectOnGrid(resolved);
  });

  it("does not displace a clean panel that is processed after a conflicting one", () => {
    // Reading order is by (y, x). The conflicting pair sits above a clean panel
    // that would be a tempting reflow target for a single-pass greedy algorithm.
    const a = makePanel("a", { x: 0, y: 0, w: 8, h: 4 });
    const b = makePanel("b", { x: 4, y: 0, w: 8, h: 4 }); // overlaps a, and runs off-grid would-be
    const cleanBelow = makePanel("cleanBelow", { x: 0, y: 4, w: 6, h: 4 });

    const resolved = resolvePanelLayouts([a, b, cleanBelow]);

    // The clean panel below keeps its exact position.
    expect(byId(resolved, "cleanBelow")).toBe(cleanBelow);
    expectNoOverlaps(resolved);
    expectOnGrid(resolved);
  });

  it("clamps off-grid widths and positions back onto the 12-column grid", () => {
    const panels = [
      makePanel("toowide", { x: 0, y: 0, w: 20, h: 4 }), // width > 12
      makePanel("offright", { x: 10, y: 6, w: 6, h: 3 }), // x + w runs past 12
      makePanel("negative", { x: -3, y: -2, w: 4, h: 2 }), // negative coords
    ];

    const resolved = resolvePanelLayouts(panels);

    expectOnGrid(resolved);
    expectNoOverlaps(resolved);
    // The over-wide panel is capped at the grid width.
    expect(byId(resolved, "toowide").layout.w).toBe(GRID_COLUMNS);
  });

  it("rounds fractional units to integers", () => {
    const panels = [
      makePanel("frac", { x: 1.6, y: 2.4, w: 5.5, h: 3.2 }),
      makePanel("other", { x: 8.1, y: 0.2, w: 3.9, h: 2.7 }),
    ];

    const resolved = resolvePanelLayouts(panels);

    expectOnGrid(resolved);
    expectNoOverlaps(resolved);
  });

  it("produces a fully valid layout for a large mixed batch", () => {
    const panels = [
      makePanel("a", { x: 0, y: 0, w: 6, h: 4 }),
      makePanel("b", { x: 0, y: 0, w: 6, h: 4 }), // dup of a
      makePanel("c", { x: 6, y: 0, w: 6, h: 4 }),
      makePanel("d", { x: 3, y: 2, w: 6, h: 4 }), // straddles a/c
      makePanel("e", { x: 0, y: 4, w: 12, h: 3 }),
      makePanel("f", { x: 11, y: 8, w: 4, h: 2 }), // off-grid right
    ];

    const resolved = resolvePanelLayouts(panels);

    expect(resolved).toHaveLength(panels.length);
    expectNoOverlaps(resolved);
    expectOnGrid(resolved);
  });
});
