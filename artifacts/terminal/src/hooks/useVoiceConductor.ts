import { useCallback, useEffect, useRef, useState } from "react";
import type { NarrationSegment } from "@workspace/api-client-react";
import { useSpeechRecognition } from "./useSpeechRecognition";

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
}

interface UseVoiceConductor {
  status: VoiceStatus;
  userLevel: number;
  agentLevel: number;
  interim: string;
  error: string | null;
  micDenied: boolean;
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
  const { active, processQuery, synthesize, onHighlight } = args;

  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [userLevel, setUserLevel] = useState(0);
  const [agentLevel, setAgentLevel] = useState(0);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [micDenied, setMicDenied] = useState(false);

  const processRef = useRef(processQuery);
  const synthRef = useRef(synthesize);
  const highlightRef = useRef(onHighlight);
  useEffect(() => {
    processRef.current = processQuery;
    synthRef.current = synthesize;
    highlightRef.current = onHighlight;
  });

  const statusRef = useRef<VoiceStatus>("idle");
  const setStatusSafe = useCallback((s: VoiceStatus) => {
    statusRef.current = s;
    setStatus(s);
  }, []);

  const busyRef = useRef(false);

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
      setError("Microphone access was denied. Enable it to use voice mode.");
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
      if (statusRef.current === "listening") setInterim(text);
    },
    onError: (kind, message) => {
      if (kind === "permission-denied") {
        setMicDenied(true);
        setStatusSafe("error");
      } else if (kind === "not-supported") {
        setStatusSafe("error");
      }
      setError(message);
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

  const handleUtterance = useCallback(async (text: string) => {
    busyRef.current = true;
    setInterim("");
    // Stop listening immediately — we have what we need.
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
          // If one segment fails, keep going.
        }
      }
    } catch {
      setError("Something went wrong. Try again.");
    } finally {
      highlightRef.current(null);
      busyRef.current = false;
      // Stay idle — don't auto-restart. User taps the orb to speak again.
      if (statusRef.current !== "error") {
        setStatusSafe("idle");
      }
    }
  }, [playSegmentAudio, setStatusSafe]);

  // --- startListening: called by the user tapping the orb ---
  const startListening = useCallback(async () => {
    if (busyRef.current) return;
    if (statusRef.current === "listening") return;
    setError(null);

    // Ensure mic access is granted before we start.
    const ok = await startMicAnalyser();
    if (!ok) return;

    if (!recognitionRef.current.supported) {
      setError("Speech recognition isn't supported in this browser. Try Chrome.");
      setStatusSafe("error");
      return;
    }
    setStatusSafe("listening");
    recognitionRef.current.start();
  }, [startMicAnalyser, setStatusSafe]);

  // --- Lifecycle: enter / exit voice mode ---
  const startVoice = useCallback(async () => {
    setError(null);
    setMicDenied(false);
    ensureCtx();
    // Begin by asking for mic permission; then sit idle.
    // User taps to speak for the first time.
    const ok = await startMicAnalyser();
    if (!ok) return;
    if (!recognitionRef.current.supported) {
      setError("Speech recognition isn't supported in this browser. Try Chrome.");
      setStatusSafe("error");
      return;
    }
    // Auto-start the first listening session so voice mode feels instant.
    setStatusSafe("listening");
    recognitionRef.current.start();
  }, [ensureCtx, startMicAnalyser, setStatusSafe]);

  const stopVoice = useCallback(() => {
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
      stopMicAnalyser();
      audioCtxRef.current?.close().catch(() => {});
    };
  }, [stopMicAnalyser]);

  const retry = useCallback(() => {
    if (active) void startVoice();
  }, [active, startVoice]);

  return { status, userLevel, agentLevel, interim, error, micDenied, retry, startListening };
}
