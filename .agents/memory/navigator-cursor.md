---
name: AI navigator cursor
description: How the chat-triggered guided-walkthrough cursor coexists with voice and grounds tours in real on-screen panels.
---

# AI navigator cursor (Agentic Terminal)

A visible AI-controlled cursor that glides across the dashboard, stops on relevant
panels in reading order, and shows a caption per stop. Triggered from chat by
intent phrases ("walk me through…", "show me what matters", "give me a tour").

## Key design decisions
- **Tours only reference panels currently in session state.** The `/api/navigate`
  endpoint builds stops from `state.get_dashboard`'s panels (LLM grounded + reading-order
  heuristic fallback), validates/dedupes panelIds. The cursor then locates each panel
  in the DOM via `[data-panel-id]`. No invented panels => no dead stops.
- **Navigator is chat-triggered, voice is its own mode.** Voice mode hides chat, so the
  two can't be invoked simultaneously. They *both* drive `highlightedPanelId`, so they
  must never run together — toggling voice on stops any running tour.
  **Why:** shared highlight state would fight if both ran.
- **Intent routing:** strip the nav phrase + filler from the query; empty remainder +
  existing panels => tour what's on screen; non-empty (a subject like "NVDA") =>
  orchestrate first, then tour after the panels render (~850ms delay).
- **Cursor uses viewport coords** (`getBoundingClientRect` centre) to match a
  `position: fixed` overlay. Overlay is `pointer-events-none` (never blocks manual use);
  only the bottom-center control bar is clickable.
- **Playback:** per stop = scrollIntoView(center) → wait ~480ms for scroll to settle →
  re-measure → move cursor (framer spring) → highlight + caption → dwell (scaled to
  caption length) → auto-advance. Manual next/prev cancels the dwell. Re-measures on
  resize. Missing panel => skip to next stop. Tour auto-dismisses after the last stop.

## Gotcha
- api-server runs WITHOUT `--reload`, so backend route/agent changes need a workflow
  restart (`artifacts/api-server: API Server`) to take effect.
