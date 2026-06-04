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
  /** Gracefully end the session, finalizing whatever was captured. */
  stop: () => void;
  /** Discard the session immediately without firing an utterance. */
  abort: () => void;
}

function getRecognitionCtor(): any {
  if (typeof window === "undefined") return null;
  return (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition || null;
}

/**
 * Push-to-talk speech recognition. Uses continuous=true so the session keeps
 * listening (accumulating speech) for as long as the user holds the control,
 * and only resolves the full utterance once stop() is called on release. Final
 * fragments are accumulated and emitted together via onUtterance on session end.
 */
export function useSpeechRecognition(options: UseSpeechRecognitionOptions): UseSpeechRecognition {
  const Ctor = getRecognitionCtor();
  const supported = !!Ctor;

  const [listening, setListening] = useState(false);

  const recognitionRef = useRef<any>(null);
  const firedRef = useRef(false); // prevent duplicate onUtterance per session
  const finalRef = useRef("");    // accumulated final transcript for this session
  const discardRef = useRef(false); // true when aborting — skip firing utterance/end

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

  const start = useCallback(() => {
    if (!supported) {
      onErrorRef.current?.("not-supported", "Speech recognition is not supported in this browser. Try Chrome.");
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
  }, [supported, buildRecognition]);

  const stop = useCallback(() => {
    try {
      // Graceful stop finalizes the current audio so onend can emit the utterance.
      recognitionRef.current?.stop();
    } catch {
      /* noop */
    }
    setListening(false);
  }, []);

  const abort = useCallback(() => {
    try {
      discardRef.current = true;
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

  return { supported, listening, start, stop, abort };
}
