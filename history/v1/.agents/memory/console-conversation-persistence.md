---
name: Console conversation persistence
description: How the Terminal Console transcript + session id survive a page reload, and how reset clears them.
---

The Console (chat) transcript and its backend session id are persisted in
`localStorage` by `artifacts/terminal/src/hooks/useConsoleConversation.ts`
(keys `agentic-terminal.console.messages.v1` / `...sessionId.v1`). `Terminal.tsx`
owns the conversation via this hook; `ChatPanel` is now a **controlled** component
(receives `messages`, no internal transcript, no `reply`/nonce machinery).

**Why session id is persisted, not the dashboard panels:** restoring the panels
visually is a separate concern (there's a dedicated "save/restore dashboard
layouts" task). We only persist the transcript + session id. On reload the
dashboard area shows the ambient dot-wave until the next command — but because the
same session id is reused, the backend's in-memory `_sessions`/`_session_history`
for that id are still intact, so a follow-up question reconnects with full context
and the panels reappear in the returned spec.

**Reset detection (frontend):** the backend mints a *new* session id on reset (see
terminal-orchestration). So `Terminal` compares the sent session id to
`result.sessionId`; if they differ, it treats it as a reset and calls
`convo.clear()` (wipes transcript + persisted session). This covers typed resets
("start fresh", "reset", etc.) and voice-triggered resets. Voice turns otherwise
stay OUT of the Console transcript but still sync the session id.

**Limitation:** session context survives a *browser refresh* (server stays up) but
NOT an api-server restart — `_sessions`/`_session_history` are in-memory only. The
transcript itself always survives (localStorage); only backend context is lost on a
server restart, after which a follow-up rebuilds fresh.
