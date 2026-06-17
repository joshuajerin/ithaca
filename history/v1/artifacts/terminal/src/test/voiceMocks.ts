import { vi } from "vitest";

/**
 * Controllable browser-API mocks for Voice Mode tests.
 *
 * `useVoiceConductor` / `useSpeechRecognition` lean on browser-only APIs that
 * jsdom doesn't provide (or only stubs): `SpeechRecognition`, `AudioContext`,
 * `navigator.mediaDevices.getUserMedia`, and `requestAnimationFrame`. These
 * mocks stand in for them and, crucially, let a test DRIVE the recognition
 * lifecycle by hand (emit a result, end the session, raise an error) — which is
 * the only way to exercise the conductor's listen -> think -> speak state
 * machine headlessly, since real SpeechRecognition can't run without a mic.
 */

// ---------------------------------------------------------------------------
// SpeechRecognition
// ---------------------------------------------------------------------------
export class MockSpeechRecognition {
  continuous = false;
  interimResults = false;
  lang = "";
  maxAlternatives = 1;

  onresult: ((event: any) => void) | null = null;
  onerror: ((event: any) => void) | null = null;
  onend: (() => void) | null = null;

  started = false;
  ended = false;
  startCalls = 0;
  stopCalls = 0;
  abortCalls = 0;

  start() {
    this.startCalls++;
    this.started = true;
    this.ended = false;
    recognitionInstances.push(this);
  }

  /** Graceful stop — Chrome finalizes audio and fires `onend`. */
  stop() {
    this.stopCalls++;
    this._end();
  }

  /** Hard abort — session ends; the hook sets a discard flag so `onend` skips emitting. */
  abort() {
    this.abortCalls++;
    this._end();
  }

  private _end() {
    if (this.ended) return;
    this.ended = true;
    this.onend?.();
  }
}

/** Every recognition instance the hook has started, in order. */
export const recognitionInstances: MockSpeechRecognition[] = [];

export function latestRecognition(): MockSpeechRecognition {
  const rec = recognitionInstances[recognitionInstances.length - 1];
  if (!rec) throw new Error("no SpeechRecognition instance has been started");
  return rec;
}

/** Simulate the recognizer hearing speech (a final or interim fragment). */
export function emitResult(rec: MockSpeechRecognition, transcript: string, isFinal: boolean) {
  rec.onresult?.({
    resultIndex: 0,
    results: { 0: { isFinal, 0: { transcript }, length: 1 }, length: 1 },
  });
}

/** Simulate a recognizer error (e.g. "network", "not-allowed"). */
export function emitError(rec: MockSpeechRecognition, error: string) {
  rec.onerror?.({ error });
}

// ---------------------------------------------------------------------------
// AudioContext (just enough for level metering + narration playback)
// ---------------------------------------------------------------------------
class MockAnalyser {
  fftSize = 2048;
  get frequencyBinCount() {
    return this.fftSize / 2;
  }
  connect() {}
  getByteTimeDomainData(_buf: Uint8Array) {
    // Leave the buffer at its zeroed state; level math reads ~0 (irrelevant to
    // the status transitions under test).
  }
}

class MockBufferSource {
  buffer: any = null;
  onended: (() => void) | null = null;
  connect() {}
  start() {
    // Narration "plays" instantly: resolve the playback promise on the microtask
    // queue so the conductor advances to the next segment / back to idle.
    queueMicrotask(() => this.onended?.());
  }
  stop() {
    this.onended?.();
  }
}

class MockAudioContext {
  state = "running";
  destination = {};
  createMediaStreamSource() {
    return { connect() {} };
  }
  createAnalyser() {
    return new MockAnalyser();
  }
  createBufferSource() {
    return new MockBufferSource();
  }
  decodeAudioData(_buf: ArrayBuffer) {
    return Promise.resolve({});
  }
  resume() {
    return Promise.resolve();
  }
  close() {
    return Promise.resolve();
  }
}

// ---------------------------------------------------------------------------
// getUserMedia (microphone permission)
// ---------------------------------------------------------------------------
function makeStream() {
  return { getTracks: () => [{ stop() {} }] };
}

let micGranted = true;

/** Make the next mic request (priming or analyser setup) be denied. */
export function denyMic() {
  micGranted = false;
}

// ---------------------------------------------------------------------------
// install / reset
// ---------------------------------------------------------------------------
export function installVoiceMocks() {
  (window as any).SpeechRecognition = MockSpeechRecognition;
  (window as any).webkitSpeechRecognition = MockSpeechRecognition;
  (window as any).AudioContext = MockAudioContext;
  (window as any).webkitAudioContext = MockAudioContext;

  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn(async () => {
        if (!micGranted) throw new DOMException("Permission denied", "NotAllowedError");
        return makeStream();
      }),
    },
  });

  // Don't actually drive the rAF level-meter loop in tests — return a handle and
  // never invoke the callback so the loop stays inert (levels are irrelevant to
  // the state machine).
  (window as any).requestAnimationFrame = vi.fn(() => 1);
  (window as any).cancelAnimationFrame = vi.fn();
}

export function resetVoiceMocks() {
  recognitionInstances.length = 0;
  micGranted = true;
}
