---
name: Voice-driven guided walkthroughs
description: How a spoken "walk me through X" runs the navigator cursor + spoken captions, advancing in sync with narration.
---

# Voice-driven guided walkthroughs (Agentic Terminal)

A tour intent spoken in Voice Mode ("walk me through NVDA") drives the navigator
cursor AND narrates each stop's caption via TTS, with the cursor advancing only
after each caption's audio finishes.

## Ownership split (who drives what)
- **The voice conductor owns the turn lifecycle + barge-in + audio playback.**
  The tour runs inside `handleUtterance` as a normal turn (status stays
  `speaking`), so the existing turnId/barge-in machinery and orb animation work
  for tours with no extra plumbing. **Why:** routing the tour as a separate
  out-of-turn flow caused an idle-flash + spurious "complete" toast and lost
  barge-in/orb-animation.
- **The navigator owns the cursor visuals** (caption card, index/total, cursor
  point, highlight). In a voice tour it runs in **narrated mode**
  (`start(tour, { narrated: true })`): the built-in dwell auto-advance is OFF and
  the cursor only moves when the conductor calls the exposed async
  `goTo(i)` (resolves once the cursor has landed). The conductor loops:
  `moveCursorTo(i)` → synth caption → `playSegmentAudio` (await = synced advance)
  → next i.
- **Terminal wires them together** via three conductor args: `prepareTour(text)`
  (returns ordered `{panelId,caption}[]` or null), `moveCursorTo` (=navigator
  `goTo`), `endTour` (=navigator `stop`). `prepareTour` reuses the chat tour's
  NAV_INTENT/tourSubject logic: bare intent + panels on screen → tour what's up;
  otherwise orchestrate (voice:false) → wait ~850ms for render → `/api/navigate`.

## Gotchas / contract
- `prepareTour` returns null for non-tour utterances → conductor falls through to
  the normal narration path (processQuery voice:true). No double orchestration.
- The conductor sets highlight via the navigator (moveCursorTo), NOT itself, in
  the tour loop — avoids double-driving the shared `highlightedPanelId`.
- Stop/dismiss: the NavigatorCursor `onStop`, when voiceMode, also calls the
  conductor's exposed `cancelNarration()` (bumps turnId + stops audio + idle) so
  dismissing the cursor silences the AI; the loop then breaks → `endTour`.
- Manual prev/next are hidden during voice tours (`manualControls={!voiceMode}`)
  because the conductor owns advancing; they'd fight the synced loop.
- `hasPanels` is mirrored to `hasPanelsRef` so `prepareTour` (a stable callback)
  reads the live value instead of a stale closure.
