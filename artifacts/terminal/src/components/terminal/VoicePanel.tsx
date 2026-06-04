import React from "react";
import { Mic, Loader2, Volume2, AlertTriangle, RefreshCw, MonitorX, ExternalLink } from "lucide-react";
import type { VoiceStatus } from "@/hooks/useVoiceConductor";
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
  /** Compact, bottom-docked control for phone-sized screens. */
  compact?: boolean;
  onRetry: () => void;
  /** Called on press/hold-start. */
  onStartListening: () => void;
  /** Called on release / pointer-cancel. */
  onStopListening: () => void;
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
  compact = false,
  onRetry,
  onStartListening,
  onStopListening,
}: VoicePanelProps) {
  // Push-to-talk: arm on press when at rest, release to finalize while listening.
  const canHoldStart = status === "idle" || status === "error";
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
              Voice Mode needs Google Chrome.
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
          /* Browser without the Web Speech API (Safari/Firefox) — make it explicit. */
          <div className="flex flex-col items-center gap-3 text-center max-w-sm">
            <MonitorX className="w-8 h-8 text-muted-foreground" strokeWidth={1.25} />
            <h2 className="font-serif text-xl tracking-tight">Voice Mode needs Chrome</h2>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Your browser doesn't support the Web Speech API used for live voice
              recognition. Open the Agentic Terminal in Google Chrome to talk to it,
              or keep using the typed command panel.
            </p>
          </div>
        ) : (
          <>
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
                  {status === "idle" && "Hold the orb and speak. Release when you're done."}
                  {status === "listening" && (interim || "Listening — release when you're done.")}
                  {status === "thinking" && "Interpreting your request…"}
                  {status === "speaking" && "Walking you through the dashboard."}
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
