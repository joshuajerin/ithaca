---
name: Terminal responsive layout
description: How the terminal dashboard + console adapt across phone/tablet/desktop breakpoints.
---

# Terminal responsive layout

Three-tier breakpoint via `useBreakpoint()` in `hooks/use-mobile.tsx`: mobile <768, tablet <1024, desktop ≥1024.

**Dashboard grid** (`Dashboard.tsx`):
- desktop — full 12-col grid honoring the AI's explicit `panel.layout.x/y` placement.
- tablet — 6-col `grid-auto-flow: row dense`; AI x/y is DROPPED (it assumes 12 cols), panels flow in reading order with halved column spans (`ceil(w/2)`, clamped 2..6). Honoring x/y on fewer columns overflows, so flow instead.
- mobile — single-column flex stack; full width, height = `max(2, h) * 110px`.

**Console** (`Terminal.tsx`):
- desktop — the fixed collapsible 400px `<aside>` sidebar.
- mobile + tablet (non-desktop) — a slide-up full-screen drawer opened from a floating "Console" button; `ChatPanel` gets an `onClose` prop that renders the X in its header. Submitting a command auto-closes the drawer so the user watches the dashboard compose.

**Why:** original redesign was desktop-only (fixed 12-col grid + 400px aside) and overflowed / left phones with no way to issue commands.

**How to apply:** when adding panel layout logic, remember tablet/mobile ignore AI x/y. New header controls should collapse labels under `sm:` (icon-only on phones).
