import { describe, it, expect, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useVoiceConductor } from "./useVoiceConductor";
import {
  denyMic,
  emitError,
  emitResult,
  latestRecognition,
  recognitionInstances,
} from "../test/voiceMocks";

/**
 * State-machine tests for the Voice Mode conductor.
 *
 * Browser SpeechRecognition can't run headless, so the recognizer, AudioContext
 * and mic are mocked (see src/test/voiceMocks.ts) and the test drives the
 * recognition lifecycle by hand. This locks down the stateful loop the task
 * cares about: idle -> listening -> thinking -> speaking -> idle, plus feedback
 * (echo) prevention and the mic-denied path.
 */

const SEGMENTS = [
  { text: "Here's your NVIDIA desk.", panelId: null },
  { text: "The price chart shows the move.", panelId: "panel-price" },
  { text: "And the latest news.", panelId: "panel-news" },
];

function setup(overrides: Partial<Parameters<typeof useVoiceConductor>[0]> = {}) {
  const processQuery = vi.fn(async () => SEGMENTS as any);
  const synthesize = vi.fn(async () => ({ audio: btoa("audio-bytes"), format: "mp3" }));
  const onHighlight = vi.fn();
  const onComplete = vi.fn();
  const hook = renderHook(() =>
    useVoiceConductor({
      active: true,
      processQuery,
      synthesize,
      onHighlight,
      onComplete,
      ...overrides,
    }),
  );
  return { ...hook, processQuery, synthesize, onHighlight, onComplete };
}

/** Drive a full hold-speak-release turn and wait for it to settle back to idle. */
async function runTurn(result: { current: ReturnType<typeof useVoiceConductor> }, utterance: string) {
  await act(async () => {
    result.current.startListening();
  });
  await waitFor(() => expect(result.current.status).toBe("listening"));

  const rec = latestRecognition();
  act(() => emitResult(rec, utterance, true));

  await act(async () => {
    result.current.stopListening();
  });
  return rec;
}

describe("useVoiceConductor", () => {
  it("enters idle once Voice Mode is activated and the mic is granted", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(result.current.error).toBeNull();
    expect(result.current.micDenied).toBe(false);
    expect(result.current.embedded).toBe(false);
  });

  it("runs the full listen -> think -> speak -> idle loop and highlights each panel", async () => {
    const { result, processQuery, synthesize, onHighlight, onComplete } = setup();
    await waitFor(() => expect(result.current.status).toBe("idle"));

    await runTurn(result, "show me nvidia");

    // The captured utterance is processed, every segment is synthesized, then
    // the turn completes back to idle (push-to-talk never re-arms on its own).
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(processQuery).toHaveBeenCalledWith("show me nvidia");
    expect(synthesize).toHaveBeenCalledTimes(SEGMENTS.length);
    expect(onComplete).toHaveBeenCalledTimes(1);

    // Panels are highlighted as they're narrated, then cleared at the end.
    expect(onHighlight).toHaveBeenCalledWith("panel-price");
    expect(onHighlight).toHaveBeenCalledWith("panel-news");
    expect(onHighlight).toHaveBeenLastCalledWith(null);
  });

  it("prevents feedback: stops the mic on capture and never auto re-arms", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.status).toBe("idle"));

    const rec = await runTurn(result, "show me nvidia");
    await waitFor(() => expect(result.current.status).toBe("idle"));

    // The recognizer that captured the utterance was stopped (so the synthesized
    // narration can't echo back into the mic)...
    expect(rec.stopCalls).toBeGreaterThanOrEqual(1);
    // ...and the loop did NOT start a fresh recognition session on its own.
    // Exactly one session existed for this single hold.
    expect(recognitionInstances).toHaveLength(1);
  });

  it("returns to idle when a listening session ends with nothing captured", async () => {
    const { result, processQuery } = setup();
    await waitFor(() => expect(result.current.status).toBe("idle"));

    await act(async () => {
      result.current.startListening();
    });
    await waitFor(() => expect(result.current.status).toBe("listening"));

    // Release without having spoken: the session ends empty -> back to idle,
    // no turn is processed.
    await act(async () => {
      result.current.stopListening();
    });
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(processQuery).not.toHaveBeenCalled();
  });

  it("surfaces the mic-denied path as an error state", async () => {
    denyMic();
    const { result } = setup();

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.micDenied).toBe(true);
    expect(result.current.error).toBeTruthy();
  });

  it("goes to error on a recognition network failure while listening", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.status).toBe("idle"));

    await act(async () => {
      result.current.startListening();
    });
    await waitFor(() => expect(result.current.status).toBe("listening"));

    act(() => emitError(latestRecognition(), "network"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBeTruthy();
  });

  it("goes to error if processing the utterance throws", async () => {
    const { result } = setup({
      processQuery: vi.fn(async () => {
        throw new Error("orchestrate failed");
      }),
    });
    await waitFor(() => expect(result.current.status).toBe("idle"));

    await runTurn(result, "break it");
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBeTruthy();
  });
});
