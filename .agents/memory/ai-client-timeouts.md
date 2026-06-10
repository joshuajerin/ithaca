---
name: AI client timeouts vs preview proxy
description: Why the api-server OpenAI client needs a bounded timeout + no retries, and how callers must fall back.
---

The Replit preview proxy returns a 502 if an upstream request hangs past its ~60s
window. The api-server OpenAI client (pointed at the AI Integrations proxy / modelfarm)
must therefore carry a client-side timeout well under that ceiling, otherwise a slow LLM
call silently hangs and the browser sees a 502 with no log line on our side.

**Rule:** any AI call that sits on a request path the user is waiting on must be bounded
AND its caller must treat a timeout exactly like any other failure (fall back to a
heuristic / non-AI path). A timeout that only raises but has no fallback still leaves the
user with an empty result.

**Why:** the orchestrate path makes a tool-enabled call requesting many tokens; with no
timeout it hangs. The existing fallbacks (`_orchestrate_llm`, `_build_narration`) already
catch `Exception`, so a bounded timeout is enough to make them kick in.

**How to apply:**
- Set `timeout` + `max_retries=0` on the shared `OpenAI` client in `app/ai.py`
  (`get_client`). `max_retries` matters — the SDK default of 2 multiplies the wait and can
  blow past the proxy window even with a per-attempt timeout.
- Audio/narration (`speak`) can use a longer per-request budget via
  `client.with_options(timeout=...)` since it is heavier, but still bounded.
- Keep all timeouts comfortably under ~60s (currently chat 30s, audio 45s,
  feature-build 55s).
- **Feature-build is a special case:** its single planning call authors TWO full
  source files and routinely takes ~45-50s, so the default 30s `CHAT_TIMEOUT`
  ALWAYS timed it out. It now passes `timeout=ai.FEATURE_BUILD_TIMEOUT` (55s) to
  `ai.chat` (which gained a per-request `timeout` param). Unlike orchestrate it has
  NO fallback, so the budget must actually fit the work — and the stream emits SSE
  heartbeats while the call runs (see self-building-features.md) so the long call
  doesn't trip the proxy.
