---
name: Terminal frontend test harness (vitest)
description: How to run/extend headless tests for the terminal's React hooks, esp. Voice Mode browser-API mocks.
---

The `terminal` artifact has a **vitest + jsdom** setup (added for the Voice Mode
conductor tests). Run with `pnpm --filter @workspace/terminal test` (also a
`voice-frontend` validation command). Config: `artifacts/terminal/vitest.config.ts`
(jsdom env, globals on, `@` alias, setup `src/test/setup.ts`). Test files match
`src/**/*.test.{ts,tsx}` and are **excluded from tsc typecheck** (`**/*.test.ts`),
so vitest globals never break `typecheck`. Note `src/test/*.ts` helpers ARE in the
typecheck include — keep them clean.

**Why a custom browser-API mock instead of real APIs:** jsdom has no
`SpeechRecognition`, no `AudioContext`, no `navigator.mediaDevices.getUserMedia`,
and real Web Speech needs a mic, so the conductor's listen→think→speak→idle loop
can't run headless. `src/test/voiceMocks.ts` stands in for all of them and lets a
test DRIVE the recognizer by hand: `latestRecognition()` grabs the instance the
hook just `.start()`ed, `emitResult(rec, text, isFinal)` feeds speech,
`emitError(rec, "network")` raises, and a recognizer `.stop()/.abort()` fires
`onend`. `denyMic()` makes the next `getUserMedia` reject (mic-denied path). The
mock `AudioContext` resolves narration playback instantly (buffer-source
`start()` → microtask `onended`), and `requestAnimationFrame` is stubbed to a
no-op so the level-meter loop stays inert.

**How to apply:** to test another browser-API-heavy hook, reuse/extend
`voiceMocks.ts` + the renderHook/act/waitFor pattern in
`useVoiceConductor.test.ts`. Remember push-to-talk never auto re-arms, so a full
turn leaves exactly one recognition instance — asserting the instance count is
how the test proves no echo/self-trigger re-listen happened.
