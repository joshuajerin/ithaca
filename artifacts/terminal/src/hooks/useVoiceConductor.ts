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
  startListening: () => void;
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
  const restartTimerRef = useRef<number | null>(null);
  // Set when a manual (push-to-talk) restart aborts an in-flight session so the
  // old session's onEnd doesn't schedule a competing auto-restart.
  const manualRestartRef = useRef(false);
  // Chrome's Web Speech service throws transient "network" errors; count them so
  // we can auto-recover a few times before giving up and surfacing the error.
  const networkRetriesRef = useRef(0);
  // A couple of retries absorb genuinely transient blips, but surface the error
  // quickly when it's a persistent block (e.g. running inside the preview iframe).
  const MAX_NETWORK_RETRIES = 2;

  // --- Audio analysis plumbing ---
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const playAnalyserRef = useRef<AnalyserNode | null>(null);
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

  // --- Speech recognition ---
  const recognition = useSpeechRecognition({
    onUtterance: (text) => {
      if (busyRef.current) return;
      void handleUtterance(text);
    },
    onInterim: (text) => {
      // Getting interim text proves the speech service connected, so clear any
      // accumulated transient network-error count.
      networkRetriesRef.current = 0;
      if (statusRef.current === "listening") setInterim(text);
    },
    onError: (kind, message) => {
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
        // Chrome's Web Speech recognizer frequently emits spurious "network"
        // errors that recover on the next attempt. Keep status as "listening" so
        // the onEnd handler auto-restarts the session, retrying a few times
        // before surfacing a hard error.
        networkRetriesRef.current += 1;
        if (networkRetriesRef.current <= MAX_NETWORK_RETRIES) {
          return;
        }
        setError("Speech recognition keeps hitting a network error. Check your connection, then tap retry.");
        setStatusSafe("error");
        return;
      }
      setError(message);
      setStatusSafe("error");
    },
    onEnd: (capturedUtterance) => {
      // A manual push-to-talk restart aborted this session on purpose; the fresh
      // session has already (re)started, so ignore this end event entirely.
      if (manualRestartRef.current) {
        manualRestartRef.current = false;
        return;
      }
      // The recognition session ended. If we were still listening and nothing
      // was captured (e.g. a silence/no-speech timeout), resume listening so the
      // experience stays hands-free instead of getting stuck on "Listening…".
      if (capturedUtterance) return;
      if (busyRef.current) return;
      if (statusRef.current === "listening") {
        setInterim("");
        setStatusSafe("idle");
        scheduleRestart();
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
      source.onended = () => {
        playAnalyserRef.current = null;
        resolve();
      };
      source.start();
    });
  }, [ensureCtx]);

  // --- startListening: begin a fresh listening session ---
  // Works both as the hands-free auto-restart and as the manual push-to-talk
  // control: when already listening, it cleanly re-arms a fresh session.
  const startListening = useCallback(async () => {
    if (!activeRef.current) return;
    if (busyRef.current) return;
    setError(null);

    // Manual re-arm while a session is already in flight: abort it, flagging the
    // abort so its onEnd doesn't schedule a competing auto-restart.
    if (statusRef.current === "listening") {
      manualRestartRef.current = true;
      recognitionRef.current.stop();
    }

    // Ensure mic access is granted before we start.
    const ok = await startMicAnalyser();
    if (!ok) return;

    if (!recognitionRef.current.supported) {
      setError("Voice Mode needs the Web Speech API. Please use Google Chrome.");
      setStatusSafe("error");
      return;
    }
    networkRetriesRef.current = 0;
    setStatusSafe("listening");
    recognitionRef.current.start();
  }, [startMicAnalyser, setStatusSafe]);

  // Resume listening shortly after a turn finishes (hands-free loop).
  const scheduleRestart = useCallback(() => {
    if (restartTimerRef.current) window.clearTimeout(restartTimerRef.current);
    restartTimerRef.current = window.setTimeout(() => {
      restartTimerRef.current = null;
      if (!activeRef.current) return;
      if (busyRef.current) return;
      if (statusRef.current !== "idle") return;
      void startListening();
    }, 900);
  }, [startListening]);

  const handleUtterance = useCallback(async (text: string) => {
    busyRef.current = true;
    setInterim("");
    // Stop listening immediately — we have the utterance and don't want the mic
    // picking up our own synthesized speech (echo / self-trigger).
    recognitionRef.current.stop();
    setStatusSafe("thinking");
    try {
      const segments = await processRef.current(text);
      setStatusSafe("speaking");
      for (const seg of segments) {
        if (!seg?.text) continue;
        highlightRef.current(seg.panelId ?? null);
        try {
          const audio = await synthRef.current(seg.text);
          await playSegmentAudio(audio.audio);
        } catch {
          // If one segment fails to synthesize, keep narrating the rest.
        }
      }
      highlightRef.current(null);
      busyRef.current = false;
      // Turn complete: announce it, drop to idle, then resume listening.
      setStatusSafe("idle");
      completeRef.current?.();
      scheduleRestart();
    } catch {
      highlightRef.current(null);
      busyRef.current = false;
      setError("Something went wrong while responding. Tap retry to try again.");
      setStatusSafe("error");
    }
  }, [playSegmentAudio, scheduleRestart, setStatusSafe]);

  // --- Lifecycle: enter / exit voice mode ---
  const startVoice = useCallback(async () => {
    setError(null);
    setMicDenied(false);
    setEmbedded(false);
    networkRetriesRef.current = 0;
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
    // Auto-start the first listening session so voice mode feels instant.
    await startListening();
  }, [ensureCtx, startListening, setStatusSafe]);

  const stopVoice = useCallback(() => {
    if (restartTimerRef.current) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    recognitionRef.current.stop();
    stopMicAnalyser();
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
      if (restartTimerRef.current) window.clearTimeout(restartTimerRef.current);
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
  };
}
