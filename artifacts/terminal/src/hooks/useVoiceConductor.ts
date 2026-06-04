import { useCallback, useEffect, useRef, useState } from "react";
import type { NarrationSegment } from "@workspace/api-client-react";
import { useSpeechRecognition } from "./useSpeechRecognition";
import { isEmbedded } from "@/lib/embed";

export type VoiceStatus =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "error";

interface UseVoiceConductorArgs {
  active: boolean;
  processQuery: (text: string) => Promise<NarrationSegment[]>;
  synthesize: (text: string) => Promise<{ audio: string; format: string }>;
  onHighlight: (panelId: string | null) => void;
  /** Fired once a full turn (listen -> think -> speak) finishes successfully. */
  onComplete?: () => void;
}

interface UseVoiceConductor {
  status: VoiceStatus;
  userLevel: number;
  agentLevel: number;
  interim: string;
  error: string | null;
  micDenied: boolean;
  /** False when the browser has no Web Speech recognition (Safari/Firefox). */
  supported: boolean;
  /** True when running inside a cross-origin iframe where the mic is blocked. */
  embedded: boolean;
  retry: () => void;
  /** Begin listening — call on press/hold-start. */
  startListening: () => void;
  /** Stop listening and process whatever was captured — call on release. */
  stopListening: () => void;
}

function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export function useVoiceConductor(args: UseVoiceConductorArgs): UseVoiceConductor {
  const { active, processQuery, synthesize, onHighlight, onComplete } = args;

  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [userLevel, setUserLevel] = useState(0);
  const [agentLevel, setAgentLevel] = useState(0);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [micDenied, setMicDenied] = useState(false);
  const [embedded, setEmbedded] = useState(false);

  const processRef = useRef(processQuery);
  const synthRef = useRef(synthesize);
  const highlightRef = useRef(onHighlight);
  const completeRef = useRef(onComplete);
  useEffect(() => {
    processRef.current = processQuery;
    synthRef.current = synthesize;
    highlightRef.current = onHighlight;
    completeRef.current = onComplete;
  });

  const statusRef = useRef<VoiceStatus>("idle");
  const setStatusSafe = useCallback((s: VoiceStatus) => {
    statusRef.current = s;
    setStatus(s);
  }, []);

  const activeRef = useRef(active);
  useEffect(() => { activeRef.current = active; });

  const busyRef = useRef(false);
  // True while the user is physically holding the orb (push-to-talk). Guards the
  // async mic-setup race: if the user releases before the mic is ready, we never
  // actually arm recognition.
  const heldRef = useRef(false);
  // Monotonic turn id. Each AI turn (think -> speak) claims an id; a barge-in
  // bumps it so the in-flight turn bails at its next checkpoint instead of
  // stomping the freshly-started listening session.
  const turnIdRef = useRef(0);

  // --- Audio analysis plumbing ---
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const playAnalyserRef = useRef<AnalyserNode | null>(null);
  // The currently-playing narration source, kept so a barge-in can stop it.
  const playSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const rafRef = useRef<number | null>(null);

  const ensureCtx = useCallback(() => {
    if (!audioCtxRef.current) {
      const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext;
      audioCtxRef.current = new Ctx();
    }
    if (audioCtxRef.current!.state === "suspended") {
      audioCtxRef.current!.resume().catch(() => {});
    }
    return audioCtxRef.current!;
  }, []);

  const readLevel = useCallback((analyser: AnalyserNode | null): number => {
    if (!analyser) return 0;
    const buf = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(1, Math.sqrt(sum / buf.length) * 3.2);
  }, []);

  useEffect(() => {
    if (!active) return;
    let mounted = true;
    const tick = () => {
      if (!mounted) return;
      const phase = statusRef.current;
      if (phase === "speaking") {
        setAgentLevel(readLevel(playAnalyserRef.current));
        setUserLevel(0);
      } else if (phase === "listening") {
        setUserLevel(readLevel(micAnalyserRef.current));
        setAgentLevel(0);
      } else {
        setUserLevel((p) => p * 0.85);
        setAgentLevel((p) => p * 0.85);
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      mounted = false;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [active, readLevel]);

  const startMicAnalyser = useCallback(async () => {
    if (micAnalyserRef.current) return true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;
      const ctx = ensureCtx();
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      src.connect(analyser);
      micAnalyserRef.current = analyser;
      return true;
    } catch {
      setMicDenied(true);
      setError("Microphone access was denied. Enable it in your browser, then retry.");
      setStatusSafe("error");
      return false;
    }
  }, [ensureCtx, setStatusSafe]);

  const stopMicAnalyser = useCallback(() => {
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    micAnalyserRef.current = null;
  }, []);

  // Request mic permission up front — on the deliberate "Voice On" tap — then
  // release the stream. On phones the permission prompt cancels a press-and-hold
  // gesture (a pointercancel fires mid-hold), so prompting during the hold makes
  // users deny by accident. Granting here means later holds re-acquire the mic
  // instantly with no prompt, keeping push-to-talk smooth.
  const primeMicPermission = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicDenied(true);
      setError("This browser can't access the microphone. Open the terminal in Google Chrome over https.");
      setStatusSafe("error");
      return false;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      setMicDenied(false);
      return true;
    } catch {
      setMicDenied(true);
      setError("Microphone access was blocked. Allow the mic for this site in your browser settings, then tap Retry.");
      setStatusSafe("error");
      return false;
    }
  }, [setStatusSafe]);

  // --- Speech recognition ---
  const recognition = useSpeechRecognition({
    onUtterance: (text) => {
      if (busyRef.current) return;
      void handleUtterance(text);
    },
    onInterim: (text) => {
      if (statusRef.current === "listening") setInterim(text);
    },
    onError: (kind, message) => {
      heldRef.current = false;
      if (kind === "permission-denied") {
        setMicDenied(true);
        setError(message);
        setStatusSafe("error");
        return;
      }
      if (kind === "not-supported") {
        setError(message);
        setStatusSafe("error");
        return;
      }
      if (kind === "network") {
        setError("Speech recognition hit a network error. Hold the orb to try again.");
        setStatusSafe("error");
        return;
      }
      setError(message);
      setStatusSafe("error");
    },
    onEnd: (capturedUtterance) => {
      // If an utterance was captured, handleUtterance has already taken over the
      // think -> speak turn, so there's nothing to do here.
      if (capturedUtterance) return;
      if (busyRef.current) return;
      // The session ended with nothing captured (user released without speaking,
      // or a silence timeout). Drop back to idle — push-to-talk never re-arms on
      // its own; the user holds the orb again to speak.
      if (statusRef.current === "listening") {
        setInterim("");
        setStatusSafe("idle");
      }
    },
  });
  const recognitionRef = useRef(recognition);
  useEffect(() => { recognitionRef.current = recognition; });

  const playSegmentAudio = useCallback(async (b64: string) => {
    const ctx = ensureCtx();
    const buffer = await ctx.decodeAudioData(base64ToArrayBuffer(b64));
    await new Promise<void>((resolve) => {
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      analyser.connect(ctx.destination);
      playAnalyserRef.current = analyser;
      playSourceRef.current = source;
      source.onended = () => {
        // Guard against clobbering a newer source (after a barge-in).
        if (playSourceRef.current === source) {
          playSourceRef.current = null;
          playAnalyserRef.current = null;
        }
        resolve();
      };
      source.start();
    });
  }, [ensureCtx]);

  // Barge-in: invalidate the in-flight turn and silence any narration in
  // progress so the user can immediately start the next prompt while the AI is
  // still thinking or speaking. The in-flight handleUtterance sees the bumped
  // turn id and bails without touching the new session's state.
  const interruptTurn = useCallback(() => {
    turnIdRef.current++;
    try {
      playSourceRef.current?.stop();
    } catch {
      /* already stopped */
    }
    playSourceRef.current = null;
    playAnalyserRef.current = null;
    busyRef.current = false;
    highlightRef.current(null);
    setAgentLevel(0);
  }, []);

  // --- startListening: begin a listening session on hold-start (push-to-talk) ---
  const startListening = useCallback(async () => {
    if (!activeRef.current) return;
    const phase = statusRef.current;
    // Barge-in: if the AI is thinking or speaking, interrupt it so the user can
    // immediately ask the next thing. Otherwise only arm from a resting state —
    // don't restart an already-active listening session.
    if (phase === "thinking" || phase === "speaking") {
      interruptTurn();
      // Drop to idle right away so a quick release during the async mic setup
      // below (the `!heldRef.current` early-return) can't strand a stale
      // thinking/speaking status with nothing actually running.
      setStatusSafe("idle");
    } else if (phase !== "idle" && phase !== "error") {
      return;
    }
    heldRef.current = true;
    setError(null);

    // Ensure mic access is granted before we start.
    const ok = await startMicAnalyser();
    if (!ok) {
      heldRef.current = false;
      return;
    }

    if (!recognitionRef.current.supported) {
      heldRef.current = false;
      setError("Voice Mode needs the Web Speech API. Please use Google Chrome.");
      setStatusSafe("error");
      return;
    }
    // The user may have released during async mic setup — don't start if so.
    if (!heldRef.current) return;
    setStatusSafe("listening");
    recognitionRef.current.start();
  }, [startMicAnalyser, setStatusSafe, interruptTurn]);

  // --- stopListening: end the session on release and finalize the utterance ---
  const stopListening = useCallback(() => {
    heldRef.current = false;
    if (statusRef.current === "listening") {
      // Graceful stop — Chrome finalizes the captured audio and the recognition
      // onEnd handler emits the full utterance (or drops to idle if empty).
      recognitionRef.current.stop();
    }
  }, []);

  const handleUtterance = useCallback(async (text: string) => {
    // Claim this turn. If a barge-in (or a later utterance) bumps turnIdRef,
    // this invocation bails at the next checkpoint instead of stomping the new
    // session's state.
    const myTurn = ++turnIdRef.current;
    busyRef.current = true;
    setInterim("");
    // Stop listening immediately — we have the utterance and don't want the mic
    // picking up our own synthesized speech (echo / self-trigger).
    recognitionRef.current.stop();
    setStatusSafe("thinking");
    try {
      const segments = await processRef.current(text);
      if (myTurn !== turnIdRef.current) return; // interrupted while thinking
      setStatusSafe("speaking");
      for (const seg of segments) {
        if (myTurn !== turnIdRef.current) break; // barged in mid-narration
        if (!seg?.text) continue;
        highlightRef.current(seg.panelId ?? null);
        try {
          const audio = await synthRef.current(seg.text);
          if (myTurn !== turnIdRef.current) break;
          await playSegmentAudio(audio.audio);
        } catch {
          // If one segment fails to synthesize, keep narrating the rest.
        }
      }
      if (myTurn !== turnIdRef.current) return; // a new turn already owns state
      highlightRef.current(null);
      busyRef.current = false;
      // Turn complete: drop to idle and wait. Push-to-talk never re-arms on its
      // own — the user holds the orb again to ask the next question.
      setStatusSafe("idle");
      completeRef.current?.();
    } catch {
      if (myTurn !== turnIdRef.current) return;
      highlightRef.current(null);
      busyRef.current = false;
      setError("Something went wrong while responding. Tap retry to try again.");
      setStatusSafe("error");
    }
  }, [playSegmentAudio, setStatusSafe]);

  // --- Lifecycle: enter / exit voice mode ---
  const startVoice = useCallback(async () => {
    setError(null);
    setMicDenied(false);
    setEmbedded(false);
    heldRef.current = false;
    // Web Speech recognition and mic capture are blocked inside cross-origin
    // iframes (the Replit preview pane / canvas). Detect that up front and
    // short-circuit before starting recognition, so we surface a clear
    // "open in a new tab" state instead of silently looping on "Listening…".
    if (isEmbedded()) {
      setEmbedded(true);
      setError("Live voice recognition is blocked inside the embedded preview.");
      setStatusSafe("error");
      return;
    }
    if (!recognitionRef.current.supported) {
      setError("Voice Mode needs the Web Speech API. Please use Google Chrome.");
      setStatusSafe("error");
      return;
    }
    ensureCtx();
    // Prime mic permission now, on this deliberate tap, so the prompt never
    // collides with a press-and-hold on mobile. If denied, primeMicPermission
    // surfaces the error/Retry state.
    const granted = await primeMicPermission();
    if (!granted) return;
    // Push-to-talk: stay idle until the user holds the orb. Do not auto-listen.
    setStatusSafe("idle");
  }, [ensureCtx, primeMicPermission, setStatusSafe]);

  const stopVoice = useCallback(() => {
    heldRef.current = false;
    turnIdRef.current++;
    recognitionRef.current.abort();
    stopMicAnalyser();
    try {
      playSourceRef.current?.stop();
    } catch {
      /* already stopped */
    }
    playSourceRef.current = null;
    playAnalyserRef.current = null;
    busyRef.current = false;
    setInterim("");
    setStatusSafe("idle");
    setUserLevel(0);
    setAgentLevel(0);
  }, [stopMicAnalyser, setStatusSafe]);

  useEffect(() => {
    if (active) {
      void startVoice();
    } else {
      stopVoice();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  useEffect(() => {
    return () => {
      stopMicAnalyser();
      audioCtxRef.current?.close().catch(() => {});
    };
  }, [stopMicAnalyser]);

  const retry = useCallback(() => {
    if (active) void startVoice();
  }, [active, startVoice]);

  return {
    status,
    userLevel,
    agentLevel,
    interim,
    error,
    micDenied,
    supported: recognition.supported,
    embedded,
    retry,
    startListening,
    stopListening,
  };
}
