import React from "react";
import { Mic, Loader2, Volume2, AlertTriangle, RefreshCw } from "lucide-react";
import type { VoiceStatus } from "@/hooks/useVoiceConductor";
import { VoiceOrb } from "./VoiceOrb";

interface VoicePanelProps {
  status: VoiceStatus;
  userLevel: number;
  agentLevel: number;
  interim: string;
  error: string | null;
  micDenied: boolean;
  onRetry: () => void;
  onStartListening: () => void;
}

const STATUS_COPY: Record<VoiceStatus, string> = {
  idle: "Tap to speak",
  listening: "Listening…",
  thinking: "Composing dashboard",
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

export function VoicePanel({
  status,
  userLevel,
  agentLevel,
  interim,
  error,
  micDenied,
  onRetry,
  onStartListening,
}: VoicePanelProps) {
  const canTap = status === "idle";

  return (
    <div className="flex flex-col h-full border-l border-border bg-[#050505]">
      <div className="p-4 border-b border-border bg-black">
        <h2 className="text-xs uppercase tracking-widest text-muted-foreground font-bold flex items-center gap-2">
          <Volume2 className="w-4 h-4" />
          Voice Mode
        </h2>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-6 gap-8">
        {/* Orb — clickable only when idle */}
        <div
          onClick={canTap ? onStartListening : undefined}
          className={canTap ? "cursor-pointer group/orb relative" : "relative"}
          title={canTap ? "Tap to speak" : undefined}
        >
          <VoiceOrb status={status} userLevel={userLevel} agentLevel={agentLevel} size={240} />
          {/* Tap hint ring */}
          {canTap && (
            <div className="absolute inset-0 rounded-full ring-1 ring-white/20 group-hover/orb:ring-white/50 transition-all duration-300 pointer-events-none" />
          )}
        </div>

        {/* Status */}
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-white">
            <StatusIcon status={status} />
            <span>{STATUS_COPY[status]}</span>
            {status === "listening" && (
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-white animate-pulse" />
            )}
          </div>

          {status === "error" ? (
            <div className="flex flex-col items-center gap-3 max-w-[260px]">
              <p className="text-xs text-muted-foreground leading-relaxed">
                {error ||
                  (micDenied
                    ? "Microphone access is blocked. Allow it in your browser, then retry."
                    : "Voice mode couldn't start.")}
              </p>
              <button
                onClick={onRetry}
                className="flex items-center gap-2 border border-border px-3 py-2 text-xs uppercase tracking-widest hover:bg-white hover:text-black transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Retry
              </button>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground leading-relaxed max-w-[260px] min-h-[2.5rem]">
              {status === "idle" && "Tap the orb to speak a command."}
              {status === "listening" && (interim || "Speak now — I'm listening.")}
              {status === "thinking" && "Interpreting your request and arranging panels…"}
              {status === "speaking" && "Walking you through the dashboard."}
            </p>
          )}
        </div>
      </div>

      <div className="p-4 bg-black border-t border-border shrink-0 text-center">
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
          Tap orb to speak · Toggle off to type
        </p>
      </div>
    </div>
  );
}
