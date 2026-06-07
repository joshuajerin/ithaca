---
name: Panel resize handles
description: How dashboard panels are user-resizable via drag handles in the CSS grid.
---

# Panel resize handles

Users resize dashboard panels by dragging edge/corner handles rendered in
`Dashboard.tsx` (right=width, bottom=height, corner=both). Resize commits new
`{w,h}` to `activeDashboard` via `onPanelResized` -> `handlePanelResized` in
`Terminal.tsx`; no data re-fetch. Neighbors reflow through the existing
`resolvePanelLayouts` pass on the next render.

**Why:** layout coords come from the AI/API and were previously fixed; users
wanted a flexible workspace.

**How to apply:**
- Grid metrics in the resize math MUST mirror the CSS: `gap-6` = 24px and
  `gridAutoRows` = 120px. Column pixel width is measured from the grid ref at
  drag start; if you change the grid's gap or row height, update the constants
  (`GRID_GAP`, `ROW_HEIGHT`) too or snapping drifts.
- Drag uses `setPointerCapture` + handlers on the handle element (not window).
  During drag, only the dragged panel is style-overridden and its framer
  `layout` animation is disabled (`layout={!isDragging}`) to stay crisp.
- Width clamps to `MIN_W..(GRID_COLUMNS - panel.x)` (can't move x on resize);
  height clamps to `MIN_H`. Resize only changes w/h, never x/y.
- Cross-session persistence is a SEPARATE concern (the "Save and restore
  dashboard layouts" task); resize only persists in live session state.
