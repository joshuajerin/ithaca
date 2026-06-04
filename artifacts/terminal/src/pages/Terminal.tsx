import React, { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  useOrchestrate,
  useSpeak,
} from "@workspace/api-client-react";
import type { DashboardSpec, NarrationSegment } from "@workspace/api-client-react";
import { Dashboard } from "@/components/terminal/Dashboard";
import { ChatPanel } from "@/components/terminal/ChatPanel";
import { VoicePanel } from "@/components/terminal/VoicePanel";
import { useVoiceConductor } from "@/hooks/useVoiceConductor";
import { FeatureRequestModal } from "@/components/terminal/FeatureRequestModal";
import { DotWaveCanvas } from "@/components/terminal/DotWaveCanvas";
import { useToast } from "@/hooks/use-toast";
import { Mic, MicOff, ChevronLeft, ChevronRight, Sparkles } from "lucide-react";

export default function Terminal() {
  const [activeDashboard, setActiveDashboard] = useState<DashboardSpec | null>(null);
  const [voiceMode, setVoiceMode] = useState(false);
  const [highlightedPanelId, setHighlightedPanelId] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  const [showFeatureModal, setShowFeatureModal] = useState(false);

  const orchestrate = useOrchestrate();
  const speak = useSpeak();
  const { toast } = useToast();

  // Keep a ref to the latest sessionId for the voice conductor callbacks.
  const sessionIdRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    sessionIdRef.current = activeDashboard?.sessionId || undefined;
  }, [activeDashboard?.sessionId]);

  const handleCommand = async (command: string) => {
    try {
      const result = await orchestrate.mutateAsync({
        data: {
          query: command,
          sessionId: sessionIdRef.current,
        },
      });
      setActiveDashboard(result);
    } catch (e) {
      console.error("Orchestration failed", e);
    }
  };

  const handlePanelRefined = (updatedPanel: any) => {
    setActiveDashboard((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        panels: prev.panels.map((p) => (p.id === updatedPanel.id ? updatedPanel : p)),
      };
    });
  };

  const hasPanels = !!activeDashboard && activeDashboard.panels.length > 0;

  // Voice flow: transcript -> orchestrate(voice) -> narration segments.
  const processVoiceQuery = useCallback(
    async (text: string): Promise<NarrationSegment[]> => {
      const result = await orchestrate.mutateAsync({
        data: { query: text, sessionId: sessionIdRef.current, voice: true },
      });
      setActiveDashboard(result);
      return result.narration ?? [];
    },
    [orchestrate],
  );

  const synthesize = useCallback(
    async (text: string) => {
      const res = await speak.mutateAsync({ data: { text } });
      return { audio: res.audio, format: res.format };
    },
    [speak],
  );

  const voice = useVoiceConductor({
    active: voiceMode,
    processQuery: processVoiceQuery,
    synthesize,
    onHighlight: setHighlightedPanelId,
    onComplete: useCallback(() => {
      toast({ title: "complete", duration: 2500 });
    }, [toast]),
  });

  return (
    <div className="flex h-screen w-full bg-black text-white overflow-hidden">
      <main className="flex-1 flex flex-col min-w-0 border-r border-border overflow-y-auto scrollbar-none">
        <header className="h-16 border-b border-border flex items-end justify-between px-8 pb-3 shrink-0 bg-black/70 backdrop-blur-sm z-10 sticky top-0">
          <div className="flex flex-col">
            <span className="font-serif text-2xl leading-none tracking-tight">Agentic&nbsp;Terminal</span>
            <span className="editorial-label text-[9px] text-muted-foreground mt-1.5">
              Synthetic Market Intelligence
            </span>
          </div>
          <div className="flex items-center gap-6">
            <div className="flex flex-col items-end">
              <span className="editorial-label text-[9px] text-muted-foreground">Session</span>
              <span className="font-serif text-sm nums-tabular mt-0.5">
                {activeDashboard?.sessionId ? activeDashboard.sessionId.slice(0, 8) : '—'}
              </span>
            </div>
            <div className="h-7 w-px bg-border" />
            <div className="flex flex-col items-end">
              <span className="editorial-label text-[9px] text-muted-foreground">Status</span>
              <span className="font-serif text-sm mt-0.5">
                {activeDashboard?.sessionId ? 'Live' : 'Ready'}
              </span>
            </div>
            <div className="h-7 w-px bg-border" />
            <button
              onClick={() => setShowFeatureModal(true)}
              className="flex items-center gap-2 px-3 py-2 editorial-label text-[9px] border border-border bg-black text-white hover:border-white transition-colors group/btn"
            >
              <Sparkles className="w-3.5 h-3.5 text-muted-foreground group-hover/btn:text-white transition-colors" strokeWidth={1.5} />
              Build Feature
            </button>
            <button
              onClick={() => setVoiceMode((v) => !v)}
              aria-pressed={voiceMode}
              className={`flex items-center gap-2 px-3 py-2 editorial-label text-[9px] border transition-colors ${
                voiceMode
                  ? "bg-white text-black border-white"
                  : "bg-black text-white border-border hover:border-white"
              }`}
            >
              {voiceMode ? <Mic className="w-3.5 h-3.5" strokeWidth={1.5} /> : <MicOff className="w-3.5 h-3.5" strokeWidth={1.5} />}
              {voiceMode ? "Voice On" : "Voice Off"}
            </button>
          </div>
        </header>

        <div className="flex-1 relative flex flex-col">
          <AnimatePresence mode="wait">
            {hasPanels ? (
              <motion.div
                key={`dashboard-${activeDashboard!.sessionId}`}
                initial={{ opacity: 0, y: 10, filter: "blur(3px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                exit={{ opacity: 0, y: -10, filter: "blur(3px)" }}
                transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                className="px-8 py-7"
              >
                <Dashboard
                  dashboard={activeDashboard!}
                  onPanelRefined={handlePanelRefined}
                  highlightedPanelId={highlightedPanelId}
                />
              </motion.div>
            ) : (
              <motion.div
                key="dotwave"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
                className="absolute inset-0"
              >
                <DotWaveCanvas />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Voice Mode is a floating overlay — the terminal stays full-screen behind it. */}
          {voiceMode && (
            <VoicePanel
              status={voice.status}
              userLevel={voice.userLevel}
              agentLevel={voice.agentLevel}
              interim={voice.interim}
              error={voice.error}
              micDenied={voice.micDenied}
              supported={voice.supported}
              embedded={voice.embedded}
              onRetry={voice.retry}
              onStartListening={voice.startListening}
            />
          )}
        </div>
      </main>

      {!voiceMode && (
        <div className="relative flex-shrink-0 flex">
          <button
            onClick={() => setChatOpen(o => !o)}
            className="absolute left-0 top-1/2 -translate-x-full -translate-y-1/2 z-20 h-12 w-5 flex items-center justify-center bg-black border border-border border-r-0 text-muted-foreground hover:text-white transition-colors"
            aria-label={chatOpen ? "Collapse chat panel" : "Expand chat panel"}
          >
            {chatOpen ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
          </button>

          <aside
            className="flex flex-col bg-black overflow-hidden border-l border-border transition-all duration-300 ease-in-out"
            style={{ width: chatOpen ? 400 : 0 }}
          >
            <div style={{ width: 400, minWidth: 400 }} className="flex flex-col h-full">
              <ChatPanel
                sessionId={activeDashboard?.sessionId}
                onCommand={handleCommand}
                isProcessing={orchestrate.isPending}
                lastSummary={activeDashboard?.summary}
              />
            </div>
          </aside>
        </div>
      )}

      <FeatureRequestModal open={showFeatureModal} onClose={() => setShowFeatureModal(false)} />
    </div>
  );
}
