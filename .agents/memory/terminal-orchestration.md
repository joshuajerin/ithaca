---
name: Terminal dashboard orchestration model
description: How the agentic terminal composes dashboards — additive-by-default, session handling, reset semantics.
---

The orchestrator (`artifacts/api-server/app/agent.py::orchestrate`) is **additive by default**:
a new natural-language query APPENDS panels to the existing session's dashboard rather than
replacing it. New panels are flow-packed starting just below existing ones
(`start_y = max(layout.y + layout.h)` over existing panels). The full combined panel list is
returned and stored, so the frontend renders existing + new together.

**Why:** users asking a follow-up (e.g. viewing Microsoft, then "get me retail investor
analysis") expect the new panels added without losing what's already on screen.

Session rules:
- The default dashboard uses sessionId `"default"` — a placeholder that must NEVER be
  accumulated onto. `orchestrate` treats `"default"` (and missing sessionId) as "mint a new
  session id," so the first real query starts clean and each page reload starts fresh.
- A **reset** intent (`_wants_reset` — word-boundary match on "reset", "wipe", "start fresh",
  "clear the/everything", "new dashboard", "clean/blank slate", "remove everything") also mints
  a brand-new session id. Minting (vs just clearing panels) ensures the prior **conversation
  history** is dropped too — otherwise stale context biases the "fresh" LLM orchestration.
  Use word boundaries so "preset"/"swipe" don't false-trigger.

Frontend (`Dashboard.tsx`): panels are wrapped in framer-motion `AnimatePresence` + `motion.div`,
keyed by `panel.id`, so appended panels fade/slide/blur in while existing ones (same key) do NOT
remount or re-animate. Grid placement (gridColumn/Row from `panel.layout`) lives on the motion
wrapper; `PanelContainer` is `h-full` and fills the cell.
