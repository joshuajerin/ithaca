import React from "react";
import { Mic, Loader2, Volume2, AlertTriangle, RefreshCw, MonitorX, ExternalLink } from "lucide-react";
import type { VoiceStatus } from "@/hooks/useVoiceConductor";
import { VoiceOrb } from "./VoiceOrb";

interface VoicePanelProps {
  status: VoiceStatus;
  userLevel: number;
  agentLevel: number;
  interim: string;
  error: string | null;
  micDenied: boolean;
  supported: boolean;
  onRetry: () => void;
  onStartListening: () => void;
}

const STATUS_COPY: Record<VoiceStatus, string> = {
  idle: "Tap to speak",
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
 * this is a compact, non-blocking control docked at the bottom-center so the
 * orb is "somewhere" rather than taking over the whole view.
 */
export function VoicePanel({
  status,
  userLevel,
  agentLevel,
  interim,
  error,
  micDenied,
  supported,
  onRetry,
  onStartListening,
}: VoicePanelProps) {
  const canTap = status === "idle";
  // Chrome's Web Speech recognizer is blocked inside cross-origin iframes (the
  // Replit preview), where it throws persistent "network" errors. Detect that so
  // we can offer an "open in a new tab" escape hatch where voice actually works.
  const inIframe = typeof window !== "undefined" && window.self !== window.top;
  const openInNewTab = () =>
    window.open(window.location.href, "_blank", "noopener,noreferrer");

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
              recognition. Open the Agentic Terminal in Google Chrome to talk to it
              hands-free, or keep using the typed command panel.
            </p>
          </div>
        ) : (
          <>
            {/* Orb — clickable only when idle */}
            <div
              onClick={canTap ? onStartListening : undefined}
              className={canTap ? "cursor-pointer group/orb relative" : "relative"}
              title={canTap ? "Tap to speak" : undefined}
            >
              <VoiceOrb status={status} userLevel={userLevel} agentLevel={agentLevel} size={132} />
              {canTap && (
                <div className="absolute inset-0 rounded-full ring-1 ring-white/20 group-hover/orb:ring-white/50 transition-all duration-300 pointer-events-none" />
              )}
            </div>

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
                  {inIframe
                    ? "Live voice recognition is blocked inside the embedded preview. Open the terminal in its own browser tab (Chrome) to talk to it hands-free."
                    : error ||
                      (micDenied
                        ? "Microphone access is blocked. Allow it in your browser, then retry."
                        : "Voice mode couldn't start.")}
                </p>
                {inIframe && error && (
                  <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground/60">
                    {error}
                  </p>
                )}
                <div className="flex items-center gap-2">
                  {inIframe && (
                    <button
                      onClick={openInNewTab}
                      className="flex items-center gap-2 bg-white text-black px-4 py-2 text-[11px] uppercase tracking-[0.2em] hover:bg-white/90 transition-colors"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      Open in new tab
                    </button>
                  )}
                  <button
                    onClick={onRetry}
                    className="flex items-center gap-2 border border-border px-4 py-2 text-[11px] uppercase tracking-[0.2em] hover:bg-white hover:text-black transition-colors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Retry
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 max-w-xs text-center">
                <p className="text-xs text-muted-foreground leading-relaxed min-h-[2rem]">
                  {status === "idle" && "Hands-free. Tap the orb or just start speaking."}
                  {status === "listening" && (interim || "Speak now — I'm listening.")}
                  {status === "thinking" && "Interpreting your request…"}
                  {status === "speaking" && "Walking you through the dashboard."}
                </p>
                {inIframe && (
                  <button
                    onClick={openInNewTab}
                    className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-muted-foreground/70 hover:text-white transition-colors"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Not responding? Open in a new tab
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
