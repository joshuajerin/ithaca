---
name: Voice Mode hands-free loop
description: Web Speech recognition quirks and the conductor turn-loop contract for the terminal's Voice Mode.
---

Voice Mode = mic (Web Speech `SpeechRecognition`) → orchestrate → TTS narration, driven by
`useVoiceConductor` over `useSpeechRecognition`.

**Quirk that breaks the loop:** with `continuous=false`, Chrome ends a session **silently on a
no-speech / silence timeout** — it fires `onend`, NOT `onerror` (`no-speech`/`aborted` are treated
as non-fatal). If the conductor only flips local `listening` state on `onend` and leaves its own
status on `"listening"`, the UI hangs forever and the orb (tappable only when idle) becomes a dead
end. **Fix/contract:** `useSpeechRecognition` exposes `onEnd(capturedUtterance)`; the conductor must
treat an end-without-utterance as a real state transition (drop to idle, then resume listening).

**Echo / self-trigger:** the mic MUST stop the instant an utterance finalizes and stay off through
thinking + speaking, or the recognizer picks up the synthesized TTS and re-triggers. Conductor stops
recognition in `handleUtterance` before going to "thinking", and only re-arms after playback resolves
(`source.onended`).

**Hands-free turn:** speak → utterance finalizes → "thinking" → narrate segments → fire `onComplete`
(Terminal shows a bottom-right `toast({title:"complete", duration})`) → idle → `scheduleRestart`
(~900ms) re-arms listening. Toggling Voice Off / `active=false` cancels the restart timer.

**Cross-browser:** Safari/Firefox lack the API. Conductor returns `supported`; VoicePanel renders an
explicit "needs Chrome" message instead of failing silently. Recognition/synthesis errors set status
"error" with a visible Retry.

**Iframe blocks Web Speech (the big one):** Chrome's `SpeechRecognition` is blocked inside
cross-origin iframes — and the Replit **preview pane is an iframe** — so it throws persistent
`network` errors there even though the very same app works fine in a normal top-level browser tab.
This is environmental; no code change makes recognition work inside the preview. **Fix/contract:**
detect the cross-origin iframe **up front** (shared `lib/embed.ts` `isEmbedded()` = cross-origin
`window.self !== window.top`) and **short-circuit `startVoice` before starting recognition** — set a
conductor `embedded` flag, never enter the "Listening…" loop. The conductor owns detection (proactive);
VoicePanel just renders the dedicated embed card off the `embedded` prop with an "Open Voice Mode in a
new tab" button (`openStandaloneTab()`). Network auto-retries stay low (MAX_NETWORK_RETRIES ~2) as a
backstop for genuine recognition errors. **Why:** waiting for network-error retries to surface the
embed guidance felt like a silent hang; detecting immediately is the contract.

**Push-to-talk fallback:** VoicePanel shows a manual "Tap to speak" / "Restart listening" button so
users aren't dependent solely on the ~900ms auto-relisten timer. `startListening` doubles as the
manual control: when already listening it aborts the in-flight session under a `manualRestartRef`
guard so the aborted session's `onEnd` doesn't schedule a competing auto-restart, then re-arms fresh.

**Runtime dep:** the generated-panels registry imports `sucrase` (browser-side TSX transpile). It must
actually be installed (`pnpm install`) — a missing install surfaces as a Vite "Failed to resolve
import 'sucrase'" that blanks the whole terminal, easy to mistake for a Voice Mode bug.

**Transient "network" errors:** Chrome's Web Speech recognizer routinely emits spurious `network`
errors that recover on the next attempt. Do NOT hard-fail on the first one — count them and keep
status on "listening" so the `onEnd` auto-restart re-arms (effectively backoff via `scheduleRestart`).
Only surface a hard error + Retry after a few consecutive failures (MAX_NETWORK_RETRIES). Reset the
counter on `onInterim` (proves the service connected), on a captured utterance, and on `startVoice`.

**Layout:** Voice Mode is a **floating overlay**, NOT a takeover. The dashboard/dotwave stays
full-screen (chat aside hidden while `voiceMode`); VoicePanel is a compact `fixed` bottom-center card
with a small orb (~132px) + status. **Why:** user explicitly rejected the orb filling the screen —
"full screen should just be the terminal, orb should be somewhere." Header/toggle stays for exit.
