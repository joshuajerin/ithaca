---
name: Console answer streaming (word-by-word)
description: How the Console streams conversational question answers via SSE, and the build-path contract that stays non-streaming.
---

The Console streams a *question* answer token-by-token; a *build* request does not
(it returns panels, not prose).

## Backend contract
- `ai.chat_stream(messages)` yields content deltas (stream=True) on the same
  bounded-timeout/no-retry client; raises if unavailable.
- `agent.orchestrate_stream(query, session_id, voice)` is the streaming twin of
  `orchestrate`. It yields event dicts: `{"type":"delta","text":...}` (question
  answer fragments) and exactly one `{"type":"done","result":{...}}` carrying the
  full DashboardSpec-shaped dict. Lifecycle + build emit only the `done` event.
- Both share `_orchestrate_prelude` (sid/base resolution), `_question_result`
  (persist + shape), `_orchestrate_build`. Keep `orchestrate` and
  `orchestrate_stream` in lockstep through these helpers — don't duplicate logic.
- `_answer_messages` builds the prompt for BOTH `_answer_question_llm` (blocking)
  and `_answer_question_stream`. Edit the prompt in one place.
- Endpoint: `POST /api/orchestrate/stream` (main.py) → StreamingResponse,
  text/event-stream, mirrors `/feature-request` SSE framing (`data: {json}\n\n`).
- **Fallback rule:** if streaming yields no tokens, `orchestrate_stream` calls the
  blocking `_answer_question` and emits it as one delta — never leave an empty answer.

## Frontend contract
- Only the plain Console command path uses streaming (`Terminal.tsx` `streamCommand`):
  fetch + ReadableStream reader, split on `\n\n`, parse `data:` lines. Voice and
  nav-tour paths stay on the blocking `useOrchestrate` mutation.
- `streamingAnswer` (live accumulated text) drives a growing assistant bubble in
  `ChatPanel.tsx`; the "Processing command" pulse hides once `streamingAnswer` is set.
  On done: adopt result, `pushReply`, clear `streamingAnswer`.
- Any stream error falls back to `orchestrate.mutateAsync` so the user still gets a full answer.
- The generated `@workspace/api-client-react` has no streaming hook — this path uses
  raw `fetch` to a relative `/api/...` URL (proxy-routed), like FeatureRequestModal.
