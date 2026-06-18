import { useCallback, useEffect, useRef, useState } from "react";

type SpeechRecognitionErrorKind =
  | "not-supported"
  | "permission-denied"
  | "network"
  | "unknown";

interface UseSpeechRecognitionOptions {
  onUtterance: (transcript: string) => void;
  onInterim?: (transcript: string) => void;
  onError?: (kind: SpeechRecognitionErrorKind, message: string) => void;
  /** Fired whenever a recognition session ends, with whether an utterance was captured. */
  onEnd?: (capturedUtterance: boolean) => void;
  /**
   * Server-side speech-to-text fallback used when the browser has no Web Speech
   * API (Safari/Firefox). When provided and the native API is missing, the hook
   * records mic audio with MediaRecorder and uploads the clip here on stop().
   */
  transcribe?: (audio: Blob) => Promise<string>;
}

interface UseSpeechRecognition {
  supported: boolean;
  listening: boolean;
  start: () => void;
  /** Gracefully end the session, finalizing whatever was captured. */
  stop: () => void;
  /** Discard the session immediately without firing an utterance. */
  abort: () => void;
}

function getRecognitionCtor(): any {
  if (typeof window === "undefined") return null;
  return (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition || null;
}

function recorderSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof (window as any).MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

/** Pick a MediaRecorder mime type the browser actually supports (Safari = mp4, Firefox = webm). */
function pickRecorderMime(): string | undefined {
  const MR: any = (window as any).MediaRecorder;
  if (!MR?.isTypeSupported) return undefined;
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
    "audio/ogg",
  ];
  for (const c of candidates) {
    if (MR.isTypeSupported(c)) return c;
  }
  return undefined;
}

/**
 * Push-to-talk speech recognition. On Chrome it uses the Web Speech API
 * (continuous=true so the session accumulates speech for as long as the user
 * holds the control, resolving the full utterance on stop()).
 *
 * On browsers without the Web Speech API (Safari/Firefox) it falls back to
 * recording the mic with MediaRecorder and uploading the clip to a server-side
 * transcription endpoint on stop(), exposing the same start/stop/abort contract.
 */
export function useSpeechRecognition(options: UseSpeechRecognitionOptions): UseSpeechRecognition {
  const Ctor = getRecognitionCtor();
  const webSpeechSupported = !!Ctor;
  // The recorded-audio fallback is usable when there's no native recognizer but
  // we can record audio AND have a transcription endpoint to send it to.
  const fallbackSupported = !webSpeechSupported && recorderSupported() && !!options.transcribe;
  const useFallback = fallbackSupported;
  const supported = webSpeechSupported || fallbackSupported;

  const [listening, setListening] = useState(false);

  const recognitionRef = useRef<any>(null);
  const firedRef = useRef(false); // prevent duplicate onUtterance per session
  const finalRef = useRef("");    // accumulated final transcript for this session
  const discardRef = useRef(false); // true when aborting — skip firing utterance/end

  // --- Recorded-audio fallback plumbing ---
  const mediaRecorderRef = useRef<any>(null);
  const recorderStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  const onUtteranceRef = useRef(options.onUtterance);
  const onInterimRef = useRef(options.onInterim);
  const onErrorRef = useRef(options.onError);
  const onEndRef = useRef(options.onEnd);
  const transcribeRef = useRef(options.transcribe);
  useEffect(() => {
    onUtteranceRef.current = options.onUtterance;
    onInterimRef.current = options.onInterim;
    onErrorRef.current = options.onError;
    onEndRef.current = options.onEnd;
    transcribeRef.current = options.transcribe;
  }, [options.onUtterance, options.onInterim, options.onError, options.onEnd, options.transcribe]);

  const buildRecognition = useCallback(() => {
    if (!Ctor) return null;
    const rec = new Ctor();
    rec.continuous = true;       // keep listening until we explicitly stop (push-to-talk)
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.maxAlternatives = 1;

    rec.onresult = (event: any) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? "";
        if (result.isFinal) {
          finalRef.current = `${finalRef.current} ${text}`.trim();
        } else {
          interim += text;
        }
      }
      const combined = `${finalRef.current} ${interim}`.trim();
      if (combined && onInterimRef.current) onInterimRef.current(combined);
    };

    rec.onerror = (event: any) => {
      const err = event?.error;
      if (err === "no-speech" || err === "aborted") return; // not fatal
      if (err === "not-allowed" || err === "service-not-allowed") {
        setListening(false);
        onErrorRef.current?.("permission-denied", "Microphone permission denied.");
        return;
      }
      if (err === "network") {
        onErrorRef.current?.("network", "Speech recognition network error.");
        return;
      }
      onErrorRef.current?.("unknown", String(err || "Speech recognition error."));
    };

    rec.onend = () => {
      setListening(false);
      if (discardRef.current) {
        discardRef.current = false;
        return;
      }
      const finalText = finalRef.current.trim();
      if (finalText && !firedRef.current) {
        firedRef.current = true;
        onUtteranceRef.current(finalText);
      }
      onEndRef.current?.(!!finalText);
    };

    return rec;
  }, [Ctor]);

  // --- Recorded-audio fallback: stop tracks + clear recorder refs. ---
  const teardownRecorder = useCallback(() => {
    recorderStreamRef.current?.getTracks().forEach((t) => t.stop());
    recorderStreamRef.current = null;
    mediaRecorderRef.current = null;
    chunksRef.current = [];
  }, []);

  const startFallback = useCallback(async () => {
    firedRef.current = false;
    discardRef.current = false;
    chunksRef.current = [];
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setListening(false);
      onErrorRef.current?.("permission-denied", "Microphone permission denied.");
      return;
    }
    recorderStreamRef.current = stream;
    const mime = pickRecorderMime();
    let recorder: any;
    try {
      recorder = mime ? new (window as any).MediaRecorder(stream, { mimeType: mime }) : new (window as any).MediaRecorder(stream);
    } catch {
      teardownRecorder();
      setListening(false);
      onErrorRef.current?.("unknown", "Could not start audio recording in this browser.");
      return;
    }
    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (e: any) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onstop = async () => {
      const stream = recorderStreamRef.current;
      stream?.getTracks().forEach((t) => t.stop());
      recorderStreamRef.current = null;
      mediaRecorderRef.current = null;
      setListening(false);

      if (discardRef.current) {
        discardRef.current = false;
        chunksRef.current = [];
        return;
      }

      const type = recorder.mimeType || mime || "audio/webm";
      const blob = new Blob(chunksRef.current, { type });
      chunksRef.current = [];

      // Nothing recorded (released instantly) — drop back to idle without firing.
      if (blob.size === 0) {
        onEndRef.current?.(false);
        return;
      }

      // Surface a transcribing hint while the clip uploads (no live interim here).
      onInterimRef.current?.("Transcribing…");

      let text = "";
      try {
        const fn = transcribeRef.current;
        if (!fn) throw new Error("no transcriber");
        text = (await fn(blob)).trim();
      } catch {
        onErrorRef.current?.("network", "Couldn't transcribe your audio. Hold the orb to try again.");
        return;
      }

      if (text && !firedRef.current) {
        firedRef.current = true;
        onUtteranceRef.current(text);
      }
      onEndRef.current?.(!!text);
    };

    try {
      recorder.start();
      setListening(true);
    } catch {
      teardownRecorder();
      setListening(false);
      onErrorRef.current?.("unknown", "Could not start audio recording in this browser.");
    }
  }, [teardownRecorder]);

  const start = useCallback(() => {
    if (!supported) {
      onErrorRef.current?.("not-supported", "Voice Mode isn't supported in this browser.");
      return;
    }
    if (useFallback) {
      void startFallback();
      return;
    }
    firedRef.current = false;
    finalRef.current = "";
    discardRef.current = false;
    // Always create a fresh instance — reusing after .stop() is unreliable in Chrome.
    recognitionRef.current = buildRecognition();
    try {
      recognitionRef.current?.start();
      setListening(true);
    } catch {
      setListening(false);
    }
  }, [supported, useFallback, startFallback, buildRecognition]);

  const stop = useCallback(() => {
    if (useFallback) {
      try {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
          // Graceful stop — onstop uploads the captured clip for transcription.
          mediaRecorderRef.current.stop();
        }
      } catch {
        /* noop */
      }
      return;
    }
    try {
      // Graceful stop finalizes the current audio so onend can emit the utterance.
      recognitionRef.current?.stop();
    } catch {
      /* noop */
    }
    setListening(false);
  }, [useFallback]);

  const abort = useCallback(() => {
    if (useFallback) {
      discardRef.current = true;
      try {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
          mediaRecorderRef.current.stop(); // onstop sees discardRef and skips upload
        } else {
          teardownRecorder();
        }
      } catch {
        teardownRecorder();
      }
      setListening(false);
      return;
    }
    try {
      discardRef.current = true;
      recognitionRef.current?.abort();
    } catch {
      /* noop */
    }
    setListening(false);
  }, [useFallback, teardownRecorder]);

  useEffect(() => {
    return () => {
      try { recognitionRef.current?.abort?.(); } catch { /* noop */ }
      try {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
          discardRef.current = true;
          mediaRecorderRef.current.stop();
        }
      } catch { /* noop */ }
      teardownRecorder();
    };
  }, [teardownRecorder]);

  return { supported, listening, start, stop, abort };
}
