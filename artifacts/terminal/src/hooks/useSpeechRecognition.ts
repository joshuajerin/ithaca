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
}

interface UseSpeechRecognition {
  supported: boolean;
  listening: boolean;
  start: () => void;
  stop: () => void;
}

function getRecognitionCtor(): any {
  if (typeof window === "undefined") return null;
  return (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition || null;
}

/**
 * Single-shot speech recognition: starts, captures one utterance, fires
 * onUtterance, then stops. Call start() again to listen for the next one.
 * Uses continuous=false so the browser automatically finalises when the user
 * stops speaking — much more reliable than manual silence detection.
 */
export function useSpeechRecognition(options: UseSpeechRecognitionOptions): UseSpeechRecognition {
  const Ctor = getRecognitionCtor();
  const supported = !!Ctor;

  const [listening, setListening] = useState(false);

  const recognitionRef = useRef<any>(null);
  const firedRef = useRef(false); // prevent duplicate onUtterance per session
  const capturedRef = useRef(false); // whether this session captured a final utterance

  const onUtteranceRef = useRef(options.onUtterance);
  const onInterimRef = useRef(options.onInterim);
  const onErrorRef = useRef(options.onError);
  const onEndRef = useRef(options.onEnd);
  useEffect(() => {
    onUtteranceRef.current = options.onUtterance;
    onInterimRef.current = options.onInterim;
    onErrorRef.current = options.onError;
    onEndRef.current = options.onEnd;
  }, [options.onUtterance, options.onInterim, options.onError, options.onEnd]);

  const buildRecognition = useCallback(() => {
    if (!Ctor) return null;
    const rec = new Ctor();
    rec.continuous = false;      // stop automatically after the user pauses
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.maxAlternatives = 1;

    rec.onresult = (event: any) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? "";
        if (result.isFinal) {
          const finalText = text.trim();
          if (finalText && !firedRef.current) {
            firedRef.current = true;
            capturedRef.current = true;
            onUtteranceRef.current(finalText);
          }
        } else {
          interim += text;
        }
      }
      if (interim && onInterimRef.current) onInterimRef.current(interim.trim());
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
      onEndRef.current?.(capturedRef.current);
    };

    return rec;
  }, [Ctor]);

  const start = useCallback(() => {
    if (!supported) {
      onErrorRef.current?.("not-supported", "Speech recognition is not supported in this browser. Try Chrome.");
      return;
    }
    firedRef.current = false;
    capturedRef.current = false;
    // Always create a fresh instance — reusing after .stop() is unreliable in Chrome.
    recognitionRef.current = buildRecognition();
    try {
      recognitionRef.current?.start();
      setListening(true);
    } catch {
      setListening(false);
    }
  }, [supported, buildRecognition]);

  const stop = useCallback(() => {
    try {
      recognitionRef.current?.abort();
    } catch {
      /* noop */
    }
    setListening(false);
  }, []);

  useEffect(() => {
    return () => {
      try { recognitionRef.current?.abort?.(); } catch { /* noop */ }
    };
  }, []);

  return { supported, listening, start, stop };
}
