import React, { useEffect, useRef } from "react";
import { Mic, Loader2, Volume2, AlertTriangle, RefreshCw, MonitorX, ExternalLink } from "lucide-react";
import type { VoiceStatus, TranscriptEntry } from "@/hooks/useVoiceConductor";
import { openStandaloneTab } from "@/lib/embed";
import { VoiceOrb } from "./VoiceOrb";

interface VoicePanelProps {
  status: VoiceStatus;
  userLevel: number;
  agentLevel: number;
  interim: string;
  error: string | null;
  micDenied: boolean;
  supported: boolean;
  embedded: boolean;
  /** Running, chronological transcript of the voice conversation this session. */
  transcript: TranscriptEntry[];
  /** Compact, bottom-docked control for phone-sized screens. */
  compact?: boolean;
  onRetry: () => void;
  /** Called on press/hold-start. */
  onStartListening: () => void;
  /** Called on release / pointer-cancel. */
  onStopListening: () => void;
}

/**
 * Scrollable history of the voice conversation: each user utterance and agent
 * narration line, oldest first. Auto-scrolls to the newest entry as the
 * conversation grows, and shows the live interim line while the user speaks.
 */
function TranscriptLog({
  transcript,
  interim,
  listening,
  compact = false,
}: {
  transcript: TranscriptEntry[];
  interim: string;
  listening: boolean;
  compact?: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const showInterim = listening && !!interim.trim();

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [transcript.length, showInterim, interim]);

  if (transcript.length === 0 && !showInterim) return null;

  return (
    <div
      className={`w-full overflow-y-auto scrollbar-none flex flex-col gap-2 text-left ${
        compact ? "max-h-28" : "max-h-44"
      }`}
      aria-label="Voice conversation transcript"
    >
      {transcript.map((entry) => (
        <div key={entry.id} className="flex flex-col gap-0.5">
          <span
            className={`editorial-label text-[8px] ${
              entry.role === "user" ? "text-white/60" : "text-muted-foreground"
            }`}
          >
            {entry.role === "user" ? "You" : "Terminal"}
          </span>
          <p
            className={`text-[11px] leading-relaxed ${
              entry.role === "user" ? "text-white" : "text-muted-foreground"
            }`}
          >
            {entry.text}
          </p>
        </div>
      ))}
      {showInterim && (
        <div className="flex flex-col gap-0.5 opacity-70">
          <span className="editorial-label text-[8px] text-white/60">You</span>
          <p className="text-[11px] leading-relaxed text-white italic">{interim}</p>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}

const STATUS_COPY: Record<VoiceStatus, string> = {
  idle: "Hold to talk",
  listening: "Listening…",
  thinking: "Thinking",
  speaking: "Speaking",
  error: "Voice unavailable",
};

function StatusIcon({ status }: { status: VoiceStatus }) {
  switch (status) {
    case "idle":      return <Mic className="w-3.5 h-3.5" />;
    case "listening": return <Mic className="w-3.5 h-3.5" />;
    case "thinking":  return <Loader2 className="w-3.5 h-3.5 animate-spin" />;
    case "speaking":  return <Volume2 className="w-3.5 h-3.5" />;
    case "error":     return <AlertTriangle className="w-3.5 h-3.5" />;
  }
}

/**
 * Floating voice overlay. The terminal/dashboard stays full-screen behind it;
 * this is a compact, non-blocking control docked at the bottom-center.
 *
 * The orb is a push-to-talk control: press and hold to listen, release to send.
 * Pointer events unify mouse + touch so it works on desktop and phones, and we
 * suppress text selection / long-press context menus while holding.
 */
export function VoicePanel({
  status,
  userLevel,
  agentLevel,
  interim,
  error,
  micDenied,
  supported,
  embedded,
  transcript,
  compact = false,
  onRetry,
  onStartListening,
  onStopListening,
}: VoicePanelProps) {
  // Push-to-talk: arm on press when at rest, release to finalize while listening.
  // Holding while the AI is thinking/speaking barges in — only an in-progress
  // "listening" session blocks a fresh hold-start.
  const canHoldStart = status !== "listening";
  const orbSize = compact ? 84 : 132;

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!canHoldStart) return;
    e.preventDefault();
    try {
      (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    } catch {
      /* noop */
    }
    onStartListening();
  };

  const handlePointerEnd = (e: React.PointerEvent) => {
    e.preventDefault();
    onStopListening();
  };

  // Keyboard push-to-talk: hold Space to talk, exactly like holding the orb.
  // Pressing Space while the agent is thinking/speaking barges in — it stops
  // playback and starts listening — so users can interrupt without reaching for
  // the orb. Release to send. We mirror the orb's gating (only arm from a
  // non-listening, non-error state) and persist the held flag in a ref so the
  // effect re-running on status changes doesn't drop a key that's still down.
  const keyHeldRef = React.useRef(false);
  React.useEffect(() => {
    if (!supported || embedded || status === "error") return;
    const isEditable = (el: EventTarget | null) => {
      const node = el as HTMLElement | null;
      if (!node || !node.tagName) return false;
      const tag = node.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || node.isContentEditable;
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      if (isEditable(e.target)) return;
      // Only arm/interrupt from a resting/thinking/speaking state — never
      // restart an active listening session (matches the orb's canHoldStart).
      if (status === "listening" || keyHeldRef.current) return;
      e.preventDefault();
      keyHeldRef.current = true;
      onStartListening();
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code !== "Space" || !keyHeldRef.current) return;
      e.preventDefault();
      keyHeldRef.current = false;
      onStopListening();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [supported, embedded, status, onStartListening, onStopListening]);

  // Embedded = running inside a cross-origin iframe (the Replit preview pane /
  // canvas) where Web Speech + mic capture are blocked. The conductor detects
  // this up front and surfaces an "open in a new tab" escape hatch.
  if (supported && embedded) {
    return (
      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-30 flex justify-center px-4">
        <div className="pointer-events-auto flex flex-col items-center gap-4 rounded-2xl border border-border bg-black/70 backdrop-blur-md px-6 py-5 shadow-2xl max-w-md w-full sm:w-auto text-center">
          <MonitorX className="w-8 h-8 text-muted-foreground" strokeWidth={1.25} />
          <h2 className="font-serif text-xl tracking-tight">Voice needs its own tab</h2>
          <p className="text-xs text-muted-foreground leading-relaxed max-w-sm">
            Microphone access isn't available inside the embedded preview. Open
            Voice Mode in its own browser tab (Chrome) to talk to the terminal.
          </p>
          <button
            onClick={() => openStandaloneTab()}
            className="flex items-center gap-2 bg-white text-black px-4 py-2 text-[11px] uppercase tracking-[0.2em] hover:bg-white/90 transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Open Voice Mode in a new tab
          </button>
        </div>
      </div>
    );
  }

  // The hold-target wrapper around the orb (shared by compact + full layouts).
  const orbControl = (
    <div
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerEnd}
      onPointerCancel={handlePointerEnd}
      onContextMenu={(e) => e.preventDefault()}
      className={`relative ${canHoldStart ? "cursor-pointer group/orb" : status === "listening" ? "cursor-pointer" : ""}`}
      style={{ touchAction: "none", userSelect: "none", WebkitUserSelect: "none" }}
      title={canHoldStart ? "Hold to talk" : undefined}
      role="button"
      aria-label="Push to talk — hold to speak"
    >
      <VoiceOrb status={status} userLevel={userLevel} agentLevel={agentLevel} size={orbSize} />
      {canHoldStart && (
        <div className="absolute inset-0 rounded-full ring-1 ring-white/20 group-hover/orb:ring-white/50 transition-all duration-300 pointer-events-none" />
      )}
    </div>
  );

  // --- Compact (phone) layout: small bottom-docked orb + terse status. ---
  if (compact) {
    return (
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-30 flex justify-center px-4">
        <div className="pointer-events-auto flex flex-col items-center gap-2 rounded-2xl border border-border bg-black/75 backdrop-blur-md px-5 py-3 shadow-2xl">
          {!supported ? (
            <div className="flex items-center gap-2 text-center text-[11px] text-muted-foreground max-w-[16rem]">
              <MonitorX className="w-4 h-4 shrink-0" strokeWidth={1.25} />
              Voice Mode needs a browser with microphone support.
            </div>
          ) : status === "error" ? (
            <div className="flex flex-col items-center gap-2 max-w-[16rem] text-center">
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {error ||
                  (micDenied
                    ? "Microphone access is blocked. Allow it, then retry."
                    : "Voice mode couldn't start.")}
              </p>
              <button
                onClick={onRetry}
                className="flex items-center gap-2 border border-border px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] hover:bg-white hover:text-black transition-colors"
              >
                <RefreshCw className="w-3 h-3" />
                Retry
              </button>
            </div>
          ) : (
            <>
              <TranscriptLog
                transcript={transcript}
                interim={interim}
                listening={status === "listening"}
                compact
              />
              {orbControl}
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-white">
                <StatusIcon status={status} />
                <span>{status === "listening" ? "Listening…" : status === "idle" ? "Hold to talk" : STATUS_COPY[status]}</span>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-30 flex justify-center px-4">
      <div className="pointer-events-auto flex flex-col items-center gap-3 rounded-2xl border border-border bg-black/70 backdrop-blur-md px-6 py-4 shadow-2xl max-w-md w-full sm:w-auto">
        {!supported ? (
          /* Browser with neither the Web Speech API nor MediaRecorder mic capture. */
          <div className="flex flex-col items-center gap-3 text-center max-w-sm">
            <MonitorX className="w-8 h-8 text-muted-foreground" strokeWidth={1.25} />
            <h2 className="font-serif text-xl tracking-tight">Voice Mode unavailable</h2>
            <p className="text-xs text-muted-foreground leading-relaxed">
              This browser can't access the microphone for voice recognition. Try a
              recent version of Chrome, Safari, or Firefox over https, or keep using
              the typed command panel.
            </p>
          </div>
        ) : (
          <>
            {/* Running conversation history — grows as you speak and the agent narrates. */}
            <TranscriptLog
              transcript={transcript}
              interim={interim}
              listening={status === "listening"}
            />

            {/* Orb — press-and-hold to talk */}
            {orbControl}

            {/* Status line */}
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white">
              <StatusIcon status={status} />
              <span>{STATUS_COPY[status]}</span>
              {status === "listening" && (
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-white animate-pulse" />
              )}
            </div>

            {status === "error" ? (
              <div className="flex flex-col items-center gap-3 max-w-sm text-center">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {error ||
                    (micDenied
                      ? "Microphone access is blocked. Allow it in your browser, then retry."
                      : "Voice mode couldn't start.")}
                </p>
                <button
                  onClick={onRetry}
                  className="flex items-center gap-2 border border-border px-4 py-2 text-[11px] uppercase tracking-[0.2em] hover:bg-white hover:text-black transition-colors"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Retry
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 max-w-xs text-center">
                <p className="text-xs text-muted-foreground leading-relaxed min-h-[2rem]">
                  {status === "idle" && "Hold the orb (or Space) and speak. Release when you're done."}
                  {status === "listening" && (interim || "Listening — release when you're done.")}
                  {status === "thinking" && "Interpreting your request… hold the orb or Space to jump in."}
                  {status === "speaking" && "Walking you through it — hold the orb or Space to interrupt."}
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
