---
name: Terminal dashboard orchestration model
description: How the agentic terminal composes dashboards — additive-by-default, session handling, reset semantics.
---

The orchestrator (`artifacts/api-server/app/agent.py::orchestrate`) is **context-aware, not
blindly additive**. On each query it first judges which existing panels still belong
(`_decide_kept_panels`): an LLM relevance call (`_relevance_llm`, JSON `{keep:[ids]}`, empty
list = drop all) with a keyword/subject heuristic fallback (`_relevance_heuristic`). Genuine
follow-ups on the same subject KEEP the relevant panels; switching to an unrelated subject
DROPS the abandoned subject's panels. Kept panels are then re-packed from the top
(`_repack` → live cursor) so removed panels leave NO grid holes, and new panels continue
flow-packing from that same cursor. Stored/returned dashboard = `kept + new`.

**Why:** asking about Samsung then about agriculture should replace, not stack. But viewing a
stock then "add retail investor analysis" / "show its news" / "compare to AMD" is a
continuation and must keep what's shown. The heuristic leans conservative (keeps all unless a
clearly different in-dataset ticker/sector appears with no continuation keyword like
add/also/compare/its).

**Gotcha:** api-server runs WITHOUT --reload, so orchestration logic changes only take effect
after restarting the `artifacts/api-server: API Server` workflow — testing via the live API
before restart silently runs the old code.

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

## Conversational Q&A intent (Console)
`orchestrate` now splits each non-voice, non-reset message into a **question** vs **build**
intent (`_classify_intent`): a cheap `_has_question_signal` gate (no signal → build, no LLM
call) then an LLM classifier (`_classify_intent_llm`, JSON `{intent}`) with a conservative
keyword fallback (`_is_question_heuristic`, defaults to build unless clearly conceptual and no
`_BUILD_CUES`). A question answers in chat (`_answer_question` → LLM grounded in on-screen
panels + last 6 history turns; honest fallback string) and returns the panel set UNCHANGED with
`{intent:"question", answer, summary:""}`; a build is unchanged and returns `{intent:"build"}`.
**Voice always builds** (intent split skipped when `voice=True`) so narration is untouched.

**Frontend contract:** `DashboardSpec` gained optional `intent` + `answer`. `Terminal.tsx`
drives the Console via a nonce-bumped `reply={text,kind,nonce}` prop (replaces the old
content-deduped `lastSummary` effect) so a question's answer ALWAYS renders even if its text
repeats. `ChatPanel` appends on nonce change; answers are labelled "Terminal · Answer".
