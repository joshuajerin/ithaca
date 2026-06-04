---
name: Voice Mode push-to-talk
description: Web Speech recognition quirks and the conductor turn contract for the terminal's push-to-talk Voice Mode.
---

Voice Mode = mic (Web Speech `SpeechRecognition`) → orchestrate → TTS narration, driven by
`useVoiceConductor` over `useSpeechRecognition`.

**Interaction model = push-to-talk (NOT hands-free).** The user presses-and-holds the orb to
listen and releases to send. The mic NEVER re-arms on its own — after a turn finishes it stays
idle until the user holds again. **Why:** the user explicitly rejected the auto re-arm loop. So
there is no `scheduleRestart`/restart timer and no network-retry auto-recovery loop anymore.

**Recognition config for push-to-talk:** `continuous=true` so a session keeps accumulating speech
for as long as held (it does NOT auto-finalize on a pause). Final fragments are accumulated and the
full utterance is emitted from `onend`, not per-`isFinal`. Two stop paths matter:
- **graceful `.stop()`** on release — Chrome finalizes the captured audio so `onend` can emit the
  accumulated utterance. Use this for hold-release.
- **`.abort()`** — discards the session without firing an utterance (sets a `discard` flag so
  `onend` skips emitting). Use this for leaving Voice Mode / cleanup.
Mixing these up is the classic bug: aborting on release throws away the user's words.

**Async mic-setup race:** `startListening` awaits `getUserMedia`. A quick tap can release before the
mic is ready. Guard with a `heldRef` set on press / cleared on release; after the await, bail if no
longer held so a fast tap never strands an armed session.

**Prime mic permission on the Voice-On gesture, NOT during the hold.** On phones the OS permission
prompt interrupts a press-and-hold — a `pointercancel` fires mid-hold, the hold is torn down, and the
user ends up tapping Deny by accident → "mic permission denied." **Fix/contract:** `startVoice` calls
`primeMicPermission()` (a `getUserMedia({audio:true})` that immediately stops the tracks) so the
prompt happens on the deliberate Voice-On tap; once granted, later holds re-acquire the mic with no
prompt. If priming is denied, surface the error + Retry and don't enter idle. Guard
`navigator.mediaDevices?.getUserMedia` (insecure context / unsupported) with a Chrome+https hint.

**Orb is a pointer hold-target:** use pointer events (`onPointerDown`/`onPointerUp`/`onPointerCancel`)
— they unify mouse + touch and avoid the double-fire of mixed mouse+touch handlers. Call
`setPointerCapture` on press so release is received even if the finger slides off. Suppress
`onContextMenu` and set `touch-action:none` + `user-select:none` so a long-press doesn't select text
or open the mobile context menu.

**no-speech end:** with `continuous=true`, releasing after silence (or a Chrome silence timeout) fires
`onend` with nothing captured (`no-speech`/`aborted` are non-fatal, not surfaced as errors). The
conductor treats end-without-utterance as a transition back to **idle** — it does NOT re-arm.

**Barge-in (interrupt the AI while it talks):** holding the orb during `thinking`/`speaking`
interrupts the current turn and immediately starts the next listen. Implemented with a monotonic
`turnIdRef`: each `handleUtterance` claims `++turnIdRef.current`; a barge-in (`interruptTurn`) bumps
it, `.stop()`s the current `AudioBufferSourceNode` (`playSourceRef`), and resets `busyRef`/highlight.
The in-flight turn re-checks `myTurn === turnIdRef.current` after every await (post-processQuery,
each segment, post-synth) and **returns without touching status/busyRef/onComplete** if superseded —
otherwise it stomps the new listening session (stray idle + toast). `source.onended` guards
`playSourceRef.current === source` before nulling so a stop() doesn't clobber a newer source.
VoicePanel gates hold-start on `status !== "listening"` (was idle/error) so only an active listen
blocks a fresh hold. **Why:** user asked to interject mid-narration to ask the next thing.

**Echo / self-trigger:** the mic MUST stop the instant an utterance finalizes and stay off through
thinking + speaking, or the recognizer picks up the synthesized TTS and re-triggers. `handleUtterance`
stops recognition before "thinking"; `startListening` refuses to arm unless status is idle/error, so
pressing the orb during thinking/speaking is a no-op.

**Cross-browser:** Safari/Firefox lack the API. Conductor returns `supported`; VoicePanel renders an
explicit "needs Chrome" message instead of failing silently. Recognition/synthesis errors set status
"error" with a visible Retry. A single `network` error now surfaces as an error (hold to retry) rather
than feeding a retry loop.

**Iframe blocks Web Speech (the big one):** Chrome's `SpeechRecognition` is blocked inside
cross-origin iframes — and the Replit **preview pane is an iframe** — so it throws persistent
`network` errors there even though the same app works in a normal top-level tab. This is
environmental; no code change makes recognition work inside the preview. **Fix/contract:** detect the
cross-origin iframe **up front** (shared `lib/embed.ts` `isEmbedded()`) and **short-circuit
`startVoice` before starting recognition** — set a conductor `embedded` flag and render the dedicated
"Open Voice Mode in a new tab" card (`openStandaloneTab()`). The conductor owns detection; VoicePanel
just reads the `embedded` prop.

**Runtime dep:** the generated-panels registry imports `sucrase` (browser-side TSX transpile). It must
actually be installed (`pnpm install`) — a missing install surfaces as a Vite "Failed to resolve
import 'sucrase'" that blanks the whole terminal, easy to mistake for a Voice Mode bug.

**Layout:** Voice Mode is a **floating overlay**, NOT a takeover. The dashboard/dotwave stays
full-screen; VoicePanel is a compact `fixed` bottom-center card. **Why:** user rejected the orb
filling the screen — "full screen should just be the terminal, orb should be somewhere." On phones
(`useIsMobile()`, breakpoint 768) the chat aside is not rendered at all (no typed fallback), the
dashboard takes full width, and VoicePanel renders in `compact` mode with a smaller orb (~84px vs
132px) docked at the bottom.
