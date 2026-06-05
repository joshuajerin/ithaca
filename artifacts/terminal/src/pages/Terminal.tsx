import React, { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  useOrchestrate,
  useSpeak,
  useNavigate,
} from "@workspace/api-client-react";
import type { DashboardSpec, NarrationSegment } from "@workspace/api-client-react";
import { Dashboard } from "@/components/terminal/Dashboard";
import { ChatPanel } from "@/components/terminal/ChatPanel";
import { VoicePanel } from "@/components/terminal/VoicePanel";
import { NavigatorCursor } from "@/components/terminal/NavigatorCursor";
import { useVoiceConductor } from "@/hooks/useVoiceConductor";
import { useNavigator } from "@/hooks/useNavigator";
import { FeatureRequestModal } from "@/components/terminal/FeatureRequestModal";
import { DotWaveCanvas } from "@/components/terminal/DotWaveCanvas";
import { useToast } from "@/hooks/use-toast";
import { useIsMobile } from "@/hooks/use-mobile";
import { Mic, MicOff, ChevronLeft, ChevronRight, Sparkles } from "lucide-react";

// Phrases that mean "drive the terminal and walk me through it" — these route to
// the AI navigator cursor instead of (or in addition to) a normal orchestration.
const NAV_INTENT =
  /\b(walk me through|walk through|guide me through|guide me|take me through|give me a tour|take me on a tour|show me around|tour (?:the|this|my)|navigate me|show me what matters|talk me through)\b/i;

// What's left of a tour request once the navigation phrasing and filler is
// stripped. Empty => a "tour what's already here" request; non-empty => there's
// a subject to build first (e.g. "walk me through NVDA").
function tourSubject(command: string): string {
  return command
    .toLowerCase()
    .replace(NAV_INTENT, " ")
    .replace(
      /\b(the|this|these|my|our|current|whole|entire|please|me|us|it|them|now|today|dashboard|board|terminal|screen|everything|around|here)\b/g,
      " ",
    )
    .replace(/[^a-z0-9 ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export default function Terminal() {
  const [activeDashboard, setActiveDashboard] = useState<DashboardSpec | null>(null);
  const [voiceMode, setVoiceMode] = useState(false);
  const [highlightedPanelId, setHighlightedPanelId] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  const [showFeatureModal, setShowFeatureModal] = useState(false);
  // The latest assistant reply to surface in the Console, carried with an
  // incrementing nonce so every reply renders — including a question's answer
  // even when panels did not change.
  const [reply, setReply] = useState<{ text: string; kind: 'answer' | 'summary'; nonce: number } | null>(null);
  const replyNonce = useRef(0);

  const pushReply = useCallback((result: DashboardSpec) => {
    const isAnswer = result.intent === "question";
    const text = (isAnswer ? result.answer : result.summary) || "";
    if (!text) return;
    replyNonce.current += 1;
    setReply({ text, kind: isAnswer ? 'answer' : 'summary', nonce: replyNonce.current });
  }, []);

  const orchestrate = useOrchestrate();
  const speak = useSpeak();
  const navigateTour = useNavigate();
  const { toast } = useToast();
  const isMobile = useIsMobile();

  // Keep a ref to the latest sessionId for the voice conductor callbacks.
  const sessionIdRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    sessionIdRef.current = activeDashboard?.sessionId || undefined;
  }, [activeDashboard?.sessionId]);

  // AI navigator cursor — drives across the dashboard, stopping on each panel.
  const navigator = useNavigator({
    onHighlight: setHighlightedPanelId,
    onComplete: useCallback(() => {
      toast({ title: "Walkthrough complete", duration: 2500 });
    }, [toast]),
  });
  const navigatorRef = useRef(navigator);
  useEffect(() => {
    navigatorRef.current = navigator;
  });

  // Fetch a tour for a session and let the cursor drive it. Tours only ever
  // reference panels that are actually on screen.
  const runTour = useCallback(
    async (sessionId: string, query: string) => {
      try {
        const tour = await navigateTour.mutateAsync({ data: { sessionId, query } });
        if (!tour.stops || tour.stops.length === 0) {
          toast({
            title: "Nothing to walk through yet",
            description: "Ask for a few panels first, then I'll guide you.",
            duration: 3000,
          });
          return;
        }
        navigatorRef.current.start(tour);
      } catch (e) {
        console.error("Navigation failed", e);
      }
    },
    [navigateTour, toast],
  );

  const handleCommand = async (command: string) => {
    // A new command always supersedes a running tour.
    if (navigatorRef.current.active) navigatorRef.current.stop();
    try {
      if (NAV_INTENT.test(command)) {
        const bare = tourSubject(command).length === 0;
        // "Walk me through this" with panels already up → tour what's on screen.
        if (bare && hasPanels && sessionIdRef.current) {
          await runTour(sessionIdRef.current, command);
          return;
        }
        // Otherwise build the dashboard for the request first, then tour it once
        // the new panels have rendered.
        const result = await orchestrate.mutateAsync({
          data: { query: command, sessionId: sessionIdRef.current },
        });
        setActiveDashboard(result);
        pushReply(result);
        window.setTimeout(() => void runTour(result.sessionId, command), 850);
        return;
      }

      const result = await orchestrate.mutateAsync({
        data: {
          query: command,
          sessionId: sessionIdRef.current,
        },
      });
      // A question answer leaves the panels untouched; a build recomposes them.
      // Either way we adopt the returned spec so the session id stays in sync.
      setActiveDashboard(result);
      pushReply(result);
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

  // Navigator and voice both drive the highlight — never let them run together.
  useEffect(() => {
    if (voiceMode && navigatorRef.current.active) navigatorRef.current.stop();
  }, [voiceMode]);

  return (
    <div className="flex h-screen w-full bg-black text-white overflow-hidden">
      <main className="flex-1 flex flex-col min-w-0 border-r border-border overflow-y-auto scrollbar-none">
        <header className="h-16 border-b border-border flex items-end justify-between px-4 sm:px-8 pb-3 shrink-0 bg-black/70 backdrop-blur-sm z-10 sticky top-0">
          <div className="flex flex-col">
            <span className="font-serif text-xl sm:text-2xl leading-none tracking-tight">Agentic&nbsp;Terminal</span>
            <span className="editorial-label text-[9px] text-muted-foreground mt-1.5">
              Synthetic Market Intelligence
            </span>
          </div>
          <div className="flex items-center gap-3 sm:gap-6">
            <div className="hidden sm:flex flex-col items-end">
              <span className="editorial-label text-[9px] text-muted-foreground">Session</span>
              <span className="font-serif text-sm nums-tabular mt-0.5">
                {activeDashboard?.sessionId ? activeDashboard.sessionId.slice(0, 8) : '—'}
              </span>
            </div>
            <div className="hidden sm:block h-7 w-px bg-border" />
            <div className="hidden sm:flex flex-col items-end">
              <span className="editorial-label text-[9px] text-muted-foreground">Status</span>
              <span className="font-serif text-sm mt-0.5">
                {activeDashboard?.sessionId ? 'Live' : 'Ready'}
              </span>
            </div>
            <div className="hidden sm:block h-7 w-px bg-border" />
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
                className="px-4 sm:px-8 py-5 sm:py-7"
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
              compact={isMobile}
              onRetry={voice.retry}
              onStartListening={voice.startListening}
              onStopListening={voice.stopListening}
            />
          )}
        </div>
      </main>

      {!voiceMode && !isMobile && (
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
                reply={reply}
              />
            </div>
          </aside>
        </div>
      )}

      <NavigatorCursor
        active={navigator.active}
        status={navigator.status}
        point={navigator.point}
        caption={navigator.caption}
        title={navigator.title}
        index={navigator.index}
        total={navigator.total}
        onStop={navigator.stop}
        onNext={navigator.next}
        onPrev={navigator.prev}
      />

      <FeatureRequestModal open={showFeatureModal} onClose={() => setShowFeatureModal(false)} />
    </div>
  );
}
