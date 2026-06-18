---
name: Panel layout collision resolution
description: Why dashboard panel overlap resolution uses a two-pass reserve-then-reflow algorithm, not single-pass greedy.
---

# Dashboard panel collision resolution

The terminal dashboard grid (12 columns, `gridAutoRows` ~120px) renders panels
at AI-assigned `{x,y,w,h}`. The AI can emit overlapping or off-grid rects, so
`resolvePanelLayouts` (in `artifacts/terminal/src/lib/layout.ts`) cleans them up
before render.

**Rule:** resolution is two-pass, both in reading order (sort by `y`, then `x`):
1. Reserve every panel that is on-grid AND non-colliding at its desired position.
2. Reflow only the leftover conflicting/off-grid panels into the first available
   top-left slot (row-major scan), without moving reserved panels.

**Why:** a single-pass greedy approach (place-or-reflow in one loop) displaced
originally-clean panels — a conflicting panel reflowed into a still-unprocessed
clean panel's spot and stole it. The task requires non-conflicting panels keep
their AI positions; only two-pass guarantees that.

**How to apply:** if you extend layout logic (e.g. resize handles, persistence),
keep the reserve-then-reflow ordering. Panels keep the same object reference when
their layout is unchanged, so don't assume the returned array is all-new.

**Responsive columns:** `resolvePanelLayouts(panels, columns = GRID_COLUMNS)` is
parameterized by effective column count — the same two-pass algorithm collapses
wide panels (`normalize` clamps `w` to `columns`) and stacks them at narrower
grids. Dashboard.tsx picks columns by viewport via `useResponsiveColumns` (1 on
phones <768px, 6 on tablets <1280px, 12 otherwise) and feeds the same count to
both the CSS `gridTemplateColumns` and the resolver — keep those two in sync.
