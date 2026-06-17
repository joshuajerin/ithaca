import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  useOrchestrate,
  useSpeak,
  useTranscribe,
  useNavigate,
} from "@workspace/api-client-react";
import type { DashboardSpec, NarrationSegment } from "@workspace/api-client-react";
import { Dashboard } from "@/components/terminal/Dashboard";
import { ChatPanel } from "@/components/terminal/ChatPanel";
import { VoicePanel } from "@/components/terminal/VoicePanel";
import { NavigatorCursor } from "@/components/terminal/NavigatorCursor";
import { AlertsNotifications } from "@/components/terminal/AlertsNotifications";
import { useVoiceConductor } from "@/hooks/useVoiceConductor";
import { useNavigator } from "@/hooks/useNavigator";
import { useConsoleConversation } from "@/hooks/useConsoleConversation";
import { useAuth } from "@/hooks/useAuth";
import { FeatureRequestModal } from "@/components/terminal/FeatureRequestModal";
import { AdminConsoleModal } from "@/components/terminal/AdminConsoleModal";
import { SavedDashboardsModal } from "@/components/terminal/SavedDashboardsModal";
import { AuditLogModal } from "@/components/terminal/AuditLogModal";
import { DotWaveCanvas } from "@/components/terminal/DotWaveCanvas";
import { useToast } from "@/hooks/use-toast";
import { useIsMobile, useBreakpoint } from "@/hooks/use-mobile";
import {
  loadVoiceSettings,
  saveVoiceSettings,
  type VoiceSettings,
} from "@/lib/voiceSettings";
import { Mic, MicOff, ChevronLeft, ChevronRight, Sparkles, Compass, CalendarClock, Command, X, LayoutGrid, LogOut, ShieldCheck, Shield } from "lucide-react";
import {
  formatEarningsCountdown,
  type EarningsRow,
} from "@/components/terminal/panels/EarningsCalendarPanel";

// Phrases that mean "drive the terminal and walk me through it" — these route to
// the AI navigator cursor instead of (or in addition to) a normal orchestration.
const NAV_INTENT =
  /\b(walk me through|walk through|guide me through|guide me|take me through|give me a tour|take me on a tour|show me around|tour (?:the|this|my)|navigate me|show me what matters|talk me through)\b/i;

// A small, tappable set of starter prompts shown over the empty-state dot-wave
// so first-time users have a concrete sense of what to type.
const EXAMPLE_PROMPTS = [
  "Show me Microsoft fundamentals",
  "Macro dashboard",
  "AAPL order book",
  "Deep dive on NVIDIA",
  "Screen the cloud & software sector",
];

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
  const [mobileConsoleOpen, setMobileConsoleOpen] = useState(false);
  const [showFeatureModal, setShowFeatureModal] = useState(false);
  const [showDashboardsModal, setShowDashboardsModal] = useState(false);
  const [showAuditModal, setShowAuditModal] = useState(false);
  const [showAdminModal, setShowAdminModal] = useState(false);
  // Voice synthesis preferences (which voice + speaking speed), persisted to
  // localStorage so the choice survives reloads.
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>(() => loadVoiceSettings());
  const voiceSettingsRef = useRef(voiceSettings);
  useEffect(() => {
    voiceSettingsRef.current = voiceSettings;
  }, [voiceSettings]);
  const updateVoiceSettings = useCallback((next: VoiceSettings) => {
    setVoiceSettings(next);
    saveVoiceSettings(next);
  }, []);
  // The latest assistant reply to surface in the Console, carried with an
  // incrementing nonce so every reply renders — including a question's answer
  // even when panels did not change.
  const [reply, setReply] = useState<{ text: string; kind: 'answer' | 'summary'; nonce: number } | null>(null);
  const replyNonce = useRef(0);
  // While a question answer is streaming in, this holds the text accumulated so
  // far so the Console can render it word-by-word. Null when nothing is streaming.
  const [streamingAnswer, setStreamingAnswer] = useState<string | null>(null);
  // True while a typed command is in flight via the streaming endpoint (the
  // useOrchestrate mutation isn't used for that path, so track it separately).
  const [streamBusy, setStreamBusy] = useState(false);

  // Ref to the command input so keyboard shortcuts can focus it from anywhere.
  const commandInputRef = useRef<HTMLInputElement>(null);
  // Open the console (if collapsed) and focus the command input. A short delay
  // lets the panel's width transition begin before the focus scrolls it in.
  const focusCommand = useCallback(() => {
    setChatOpen(true);
    window.setTimeout(() => commandInputRef.current?.focus(), 80);
  }, []);

  // The Console conversation (transcript + the backend session id it belongs
  // to) is persisted in localStorage so it survives a page reload. Reusing the
  // stored session id keeps follow-up questions in context with the same
  // backend session.
  const { identity, logout, can } = useAuth();
  const convo = useConsoleConversation(identity?.user.id);

  // Surface an assistant reply in the UI with a fresh nonce.
  const pushReply = useCallback((spec: DashboardSpec) => {
    const isAnswer = spec.intent === "question";
    const text = (isAnswer ? spec.answer : spec.summary) || "";
    if (text) {
      replyNonce.current += 1;
      setReply({ text, kind: isAnswer ? 'answer' : 'summary', nonce: replyNonce.current });
    }
  }, []);

  // Adopt a backend result into the conversation: keep the session id in sync,
  // surface the assistant reply in the Console, and — when a reset minted a new
  // session id — wipe the persisted transcript so the Console starts fresh too.
  const adoptResult = useCallback(
    (result: DashboardSpec, sentSessionId: string | undefined) => {
      const wasReset =
        !!sentSessionId &&
        !!result.sessionId &&
        result.sessionId !== sentSessionId;
      if (wasReset) {
        convo.clear();
        convo.setSessionId(result.sessionId);
        return;
      }
      convo.setSessionId(result.sessionId);
      // When the AI was slow/unavailable the server flags the response; surface
      // an honest notice (before the summary) so the user knows why the
      // dashboard may look simpler.
      if (result.degraded) {
        convo.addNoticeMessage(result.note || "AI was slow — showing a quick dashboard.");
      }
      const isAnswer = result.intent === "question";
      const text = (isAnswer ? result.answer : result.summary) || "";
      if (text) convo.addAssistantMessage(text, isAnswer ? "answer" : "summary");
      pushReply(result);
    },
    [convo, pushReply],
  );

  const orchestrate = useOrchestrate();
  const speak = useSpeak();
  const transcribe = useTranscribe();
  const navigateTour = useNavigate();
  const { toast } = useToast();
  const isMobile = useIsMobile();
  const breakpoint = useBreakpoint();
  const isDesktop = breakpoint === "desktop";

  const handleAlertEvent = useCallback(
    (ev: { message: string }) =>
      toast({ title: "Trade Flow Alert", description: ev.message, duration: 6000 }),
    [toast],
  );

  // Keep a ref to the latest sessionId for the voice conductor callbacks. The
  // source of truth is the persisted conversation, so a reloaded page keeps
  // talking to the same backend session.
  const sessionIdRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    sessionIdRef.current = convo.sessionId || undefined;
  }, [convo.sessionId]);

  // Whether any panels are currently on screen — mirrored to a ref so the voice
  // conductor's tour callbacks (which close over a stale render) can read it.
  const hasPanelsRef = useRef(false);

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
    // Record the operator's message immediately so the Console (and its
    // persisted transcript) reflects what was asked.
    convo.addUserMessage(command);
    const sent = sessionIdRef.current;
    try {
      if (NAV_INTENT.test(command)) {
        const bare = tourSubject(command).length === 0;
        // "Walk me through this" with panels already up → tour what's on screen.
        if (bare && hasPanels && sent) {
          await runTour(sent, command);
          return;
        }
        // Otherwise build the dashboard for the request first, then tour it once
        // the new panels have rendered.
        const result = await orchestrate.mutateAsync({
          data: { query: command, sessionId: sent },
        });
        setActiveDashboard(result);
        adoptResult(result, sent);
        window.setTimeout(() => void runTour(result.sessionId, command), 850);
        return;
      }

      await streamCommand(command, sent);
    } catch (e) {
      console.error("Orchestration failed", e);
    }
  };

  // Clicking a cell in the IV surface heatmap builds the matching option —
  // closing the loop from analysis to trade construction. We route through the
  // same orchestration flow as a typed command, so the new Options Strategy
  // panel appends to the current session.
  const handleBuildOption = ({ symbol, strike, expiry }: { symbol: string; strike: number; expiry: string; iv: number }) => {
    // Phrased to route to the options_strategy skill — deliberately avoiding the
    // verb "build" + "strategy", which the backend's deterministic lifecycle
    // handler intercepts as a "create a trading strategy" command.
    const query = `Price a long call on ${symbol} at the $${strike} strike for the ${expiry} expiry`;
    void handleCommand(query);
  };

  // Run a plain Console command against the streaming endpoint. A question's
  // answer renders word-by-word as deltas arrive; a build emits only the final
  // result. Any failure falls back to the blocking /orchestrate path so the user
  // still gets a complete answer.
  const streamCommand = useCallback(
    async (command: string, sent: string | undefined) => {
      setStreamBusy(true);
      setStreamingAnswer(null);
      let acc = "";
      let finalResult: DashboardSpec | null = null;
      try {
        const res = await fetch("/api/orchestrate/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: command, sessionId: sent }),
        });
        if (!res.ok || !res.body) throw new Error(`stream failed (${res.status})`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split("\n\n");
          buffer = chunks.pop() ?? "";
          for (const chunk of chunks) {
            const line = chunk.trim();
            if (!line.startsWith("data:")) continue;
            const payload = line.slice(5).trim();
            if (!payload) continue;
            let ev: any;
            try {
              ev = JSON.parse(payload);
            } catch {
              continue;
            }
            if (ev.type === "delta" && typeof ev.text === "string") {
              acc += ev.text;
              setStreamingAnswer(acc);
            } else if (ev.type === "done" && ev.result) {
              finalResult = ev.result as DashboardSpec;
            } else if (ev.type === "error") {
              throw new Error(ev.message || "stream error");
            }
          }
        }

        if (!finalResult) throw new Error("stream ended without a result");
        // Adopt the final spec (keeps the session id in sync) and commit the
        // reply into the persisted transcript, then clear the live streaming text.
        setActiveDashboard(finalResult);
        adoptResult(finalResult, sent);
        setStreamingAnswer(null);
      } catch (e) {
        // Graceful fallback: render the answer all at once via the blocking path.
        setStreamingAnswer(null);
        const result = await orchestrate.mutateAsync({
          data: { query: command, sessionId: sent },
        });
        setActiveDashboard(result);
        adoptResult(result, sent);
      } finally {
        setStreamBusy(false);
      }
    },
    [orchestrate, adoptResult],
  );

  const handlePanelRefined = (updatedPanel: any) => {
    setActiveDashboard((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        panels: prev.panels.map((p) => (p.id === updatedPanel.id ? updatedPanel : p)),
      };
    });
  };

  // User dragged a panel's resize handle — apply the new grid size immediately,
  // in place, without re-fetching panel data.
  const handlePanelResized = useCallback(
    (panelId: string, size: { w: number; h: number }) => {
      setActiveDashboard((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          panels: prev.panels.map((p) =>
            p.id === panelId ? { ...p, layout: { ...p.layout, w: size.w, h: size.h } } : p,
          ),
        };
      });
    },
    [],
  );

  const hasPanels = !!activeDashboard && activeDashboard.panels.length > 0;
  useEffect(() => {
    hasPanelsRef.current = hasPanels;
  }, [hasPanels]);

  // Earnings alert: surface a banner when any earnings_calendar panel on the
  // active dashboard flags a watched company reporting within 24 hours.
  const imminentReports = useMemo<EarningsRow[]>(() => {
    if (!activeDashboard) return [];
    const collected: EarningsRow[] = [];
    for (const p of activeDashboard.panels) {
      if (p.type === "earnings_calendar") {
        const imm = ((p.data as any)?.imminent as EarningsRow[]) || [];
        collected.push(...imm);
      }
    }
    const seen = new Set<string>();
    const uniq = collected.filter(r => {
      if (seen.has(r.symbol)) return false;
      seen.add(r.symbol);
      return true;
    });
    uniq.sort((a, b) => a.hoursUntil - b.hoursUntil);
    return uniq;
  }, [activeDashboard]);

  const imminentKey = imminentReports.map(r => r.symbol).join(",");
  const [dismissedEarningsKey, setDismissedEarningsKey] = useState<string | null>(null);
  const showEarningsBanner = imminentReports.length > 0 && dismissedEarningsKey !== imminentKey;

  // A live clock so the banner countdown ticks while it is visible.
  const [bannerNow, setBannerNow] = useState(() => Date.now());
  useEffect(() => {
    if (!showEarningsBanner) return;
    const id = window.setInterval(() => setBannerNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [showEarningsBanner]);

  // Voice flow: transcript -> orchestrate(voice) -> narration segments.
  const processVoiceQuery = useCallback(
    async (text: string): Promise<NarrationSegment[]> => {
      const sent = sessionIdRef.current;
      const result = await orchestrate.mutateAsync({
        data: { query: text, sessionId: sent, voice: true },
      });
      setActiveDashboard(result);
      // Voice turns stay out of the Console transcript, but the session id must
      // still track so a later typed follow-up reuses the same backend session.
      // A voice-triggered reset also clears the persisted conversation.
      const wasReset = !!sent && !!result.sessionId && result.sessionId !== sent;
      if (wasReset) convo.clear();
      convo.setSessionId(result.sessionId);
      return result.narration ?? [];
    },
    [orchestrate, convo],
  );

  const synthesize = useCallback(
    async (text: string) => {
      const { voice, speed } = voiceSettingsRef.current;
      const res = await speak.mutateAsync({ data: { text, voice, speed } });
      return { audio: res.audio, format: res.format };
    },
    [speak],
  );

  // Voice guided walkthrough: if a spoken request is a tour intent, build the
  // dashboard when needed, start the cursor in narrated mode, and hand the
  // ordered captions back to the conductor to speak as the cursor lands on each
  // stop. Returns null for a normal query so regular narration runs instead.
  const prepareVoiceTour = useCallback(
    async (text: string): Promise<{ panelId: string; caption: string }[] | null> => {
      if (!NAV_INTENT.test(text)) return null;
      const bare = tourSubject(text).length === 0;
      let sessionId = sessionIdRef.current;
      // "Walk me through this" with panels already up → tour what's on screen.
      // Otherwise build the dashboard for the subject first, then wait for the
      // new panels to render so the cursor can find them in the DOM.
      if (!(bare && hasPanelsRef.current && sessionId)) {
        const result = await orchestrate.mutateAsync({
          data: { query: text, sessionId },
        });
        setActiveDashboard(result);
        sessionId = result.sessionId;
        await new Promise((r) => window.setTimeout(r, 850));
      }
      if (!sessionId) return null;
      const tour = await navigateTour.mutateAsync({ data: { sessionId, query: text } });
      const stops = (tour.stops || []).filter((s) => s && s.panelId && s.caption);
      if (stops.length === 0) {
        toast({
          title: "Nothing to walk through yet",
          description: "Ask for a few panels first, then I'll guide you.",
          duration: 3000,
        });
        return null;
      }
      navigatorRef.current.start({ ...tour, stops }, { narrated: true });
      return stops.map((s) => ({ panelId: s.panelId, caption: s.caption }));
    },
    [orchestrate, navigateTour, toast],
  );

  const moveCursorTo = useCallback(
    (index: number) => navigatorRef.current.goTo(index),
    [],
  );
  const endVoiceTour = useCallback(() => navigatorRef.current.stop(), []);

  // Server-side STT for browsers without the Web Speech API (Safari/Firefox):
  // base64-encode the recorded clip and send it to /transcribe.
  const transcribeAudio = useCallback(
    async (blob: Blob): Promise<string> => {
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let binary = "";
      const chunk = 0x8000;
      for (let i = 0; i < bytes.length; i += chunk) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
      }
      const base64 = btoa(binary);
      const res = await transcribe.mutateAsync({
        data: { audio: base64, mimeType: blob.type || undefined },
      });
      return res.text ?? "";
    },
    [transcribe],
  );

  const voice = useVoiceConductor({
    active: voiceMode,
    processQuery: processVoiceQuery,
    synthesize,
    transcribe: transcribeAudio,
    onHighlight: setHighlightedPanelId,
    onComplete: useCallback(() => {
      toast({ title: "complete", duration: 2500 });
    }, [toast]),
    prepareTour: prepareVoiceTour,
    moveCursorTo,
    endTour: endVoiceTour,
  });
  const voiceRef = useRef(voice);
  useEffect(() => {
    voiceRef.current = voice;
  });

  // Navigator and voice both drive the highlight — never let them run together.
  useEffect(() => {
    if (voiceMode && navigatorRef.current.active) navigatorRef.current.stop();
  }, [voiceMode]);

  // Power-user keyboard shortcuts:
  //   "/" or ⌘/Ctrl+K  → focus the command input from anywhere
  //   Esc              → blur the input if focused, else toggle the console
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (isMobile) return;
      const target = e.target as HTMLElement | null;
      const editable =
        !!target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);

      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        if (voiceMode) return;
        e.preventDefault();
        focusCommand();
        return;
      }

      if (e.key === "/" && !editable && !e.metaKey && !e.ctrlKey && !e.altKey) {
        if (voiceMode) return;
        e.preventDefault();
        focusCommand();
        return;
      }

      if (e.key === "Escape") {
        if (showFeatureModal || voiceMode) return;
        if (document.activeElement === commandInputRef.current) {
          commandInputRef.current?.blur();
        } else {
          setChatOpen((o) => !o);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isMobile, voiceMode, showFeatureModal, focusCommand]);

  const modLabel =
    typeof window !== "undefined" &&
    /Mac|iPhone|iPad/.test(window.navigator.platform)
      ? "⌘K"
      : "Ctrl K";

  return (
    <div className="flex flex-col h-screen w-full bg-black text-white overflow-hidden">
      <div className="flex flex-1 min-h-0 w-full">
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
                {convo.sessionId ? convo.sessionId.slice(0, 8) : '—'}
              </span>
            </div>
            <div className="hidden sm:block h-7 w-px bg-border" />
            <div className="hidden sm:flex flex-col items-end">
              <span className="editorial-label text-[9px] text-muted-foreground">Status</span>
              <span className="font-serif text-sm mt-0.5">
                {convo.sessionId ? 'Live' : 'Ready'}
              </span>
            </div>
            <div className="hidden sm:block h-7 w-px bg-border" />
            {hasPanels && (
              <button
                onClick={() => {
                  if (sessionIdRef.current) {
                    void runTour(sessionIdRef.current, "walk me through this dashboard");
                  }
                }}
                className="flex items-center gap-2 px-3 py-2 editorial-label text-[9px] border border-border bg-black text-white hover:border-white transition-colors group/btn"
              >
                <Compass className="w-3.5 h-3.5 text-muted-foreground group-hover/btn:text-white transition-colors" strokeWidth={1.5} />
                Tour
              </button>
            )}
            <button
              onClick={() => setShowDashboardsModal(true)}
              disabled={!can("dashboard.save")}
              title={can("dashboard.save") ? undefined : "Saving dashboards requires the analyst role or higher"}
              className="flex items-center gap-2 px-3 py-2 editorial-label text-[9px] border border-border bg-black text-white hover:border-white transition-colors group/btn disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-border"
            >
              <LayoutGrid className="w-3.5 h-3.5 text-muted-foreground group-hover/btn:text-white transition-colors" strokeWidth={1.5} />
              Dashboards
            </button>
            {identity?.user.role === "admin" && (
              <button
                onClick={() => setShowAuditModal(true)}
                className="flex items-center gap-2 px-2.5 sm:px-3 py-2 editorial-label text-[9px] border border-border bg-black text-white hover:border-white transition-colors group/btn"
              >
                <ShieldCheck className="w-3.5 h-3.5 text-muted-foreground group-hover/btn:text-white transition-colors" strokeWidth={1.5} />
                <span className="hidden sm:inline">Audit</span>
              </button>
            )}
            <button
              onClick={() => setShowFeatureModal(true)}
              disabled={!can("feature.build")}
              title={can("feature.build") ? undefined : "Building features requires the admin role"}
              className="flex items-center gap-2 px-2.5 sm:px-3 py-2 editorial-label text-[9px] border border-border bg-black text-white hover:border-white transition-colors group/btn disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-border"
            >
              <Sparkles className="w-3.5 h-3.5 text-muted-foreground group-hover/btn:text-white transition-colors" strokeWidth={1.5} />
              <span className="hidden sm:inline">Build Feature</span>
            </button>
            {can("user.manage") && (
              <button
                onClick={() => setShowAdminModal(true)}
                title="Firm admin console"
                className="flex items-center gap-2 px-2.5 sm:px-3 py-2 editorial-label text-[9px] border border-border bg-black text-white hover:border-white transition-colors group/btn"
              >
                <Shield className="w-3.5 h-3.5 text-muted-foreground group-hover/btn:text-white transition-colors" strokeWidth={1.5} />
                <span className="hidden sm:inline">Admin</span>
              </button>
            )}
            <button
              onClick={() => setVoiceMode((v) => !v)}
              aria-pressed={voiceMode}
              className={`flex items-center gap-2 px-2.5 sm:px-3 py-2 editorial-label text-[9px] border transition-colors ${
                voiceMode
                  ? "bg-white text-black border-white"
                  : "bg-black text-white border-border hover:border-white"
              }`}
            >
              {voiceMode ? <Mic className="w-3.5 h-3.5" strokeWidth={1.5} /> : <MicOff className="w-3.5 h-3.5" strokeWidth={1.5} />}
              <span className="hidden sm:inline">{voiceMode ? "Voice On" : "Voice Off"}</span>
            </button>
            {identity && (
              <>
                <div className="hidden md:block h-7 w-px bg-border" />
                <div className="hidden md:flex flex-col items-end max-w-[180px]">
                  <span className="font-serif text-sm leading-none truncate w-full text-right">
                    {identity.user.name}
                  </span>
                  <span className="editorial-label text-[9px] text-muted-foreground mt-1 truncate w-full text-right">
                    {identity.firm.name} · {identity.user.role}
                  </span>
                </div>
                <button
                  onClick={() => void logout()}
                  title="Sign out"
                  aria-label="Sign out"
                  className="flex items-center gap-2 px-2.5 sm:px-3 py-2 editorial-label text-[9px] border border-border bg-black text-white hover:border-white transition-colors group/btn"
                >
                  <LogOut className="w-3.5 h-3.5 text-muted-foreground group-hover/btn:text-white transition-colors" strokeWidth={1.5} />
                  <span className="hidden sm:inline">Sign out</span>
                </button>
              </>
            )}
          </div>
        </header>

        <div className="flex-1 relative flex flex-col">
          <AnimatePresence>
            {showEarningsBanner && (
              <motion.div
                key={`earnings-alert-${imminentKey}`}
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                className="mx-4 sm:mx-8 mt-4 flex items-center gap-3 border border-amber-400/50 bg-amber-400/10 px-3 py-2"
              >
                <CalendarClock className="w-4 h-4 text-amber-400 shrink-0" strokeWidth={1.8} />
                <div className="flex-1 min-w-0 text-[11px] leading-tight text-amber-200">
                  <span className="font-bold uppercase tracking-wider text-amber-300">Earnings alert</span>
                  {" — "}
                  {imminentReports.length === 1
                    ? `${imminentReports[0].name} (${imminentReports[0].symbol}) reports ${imminentReports[0].timingLabel.toLowerCase()}`
                    : `${imminentReports.length} watched companies report within 24h`}
                  {": "}
                  {imminentReports.slice(0, 4).map((r, i) => (
                    <span key={r.symbol}>
                      {i > 0 && ", "}
                      <span className="font-bold">{r.symbol}</span>{" "}
                      <span className="nums-tabular">{formatEarningsCountdown(r.reportDateTime, bannerNow)}</span>
                    </span>
                  ))}
                  {imminentReports.length > 4 && ` +${imminentReports.length - 4} more`}
                </div>
                <button
                  onClick={() => setDismissedEarningsKey(imminentKey)}
                  className="shrink-0 text-amber-400/70 hover:text-amber-300 transition-colors"
                  aria-label="Dismiss earnings alert"
                >
                  <X className="w-3.5 h-3.5" strokeWidth={2} />
                </button>
              </motion.div>
            )}
          </AnimatePresence>
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
                  onPanelResized={handlePanelResized}
                  highlightedPanelId={highlightedPanelId}
                  onBuildOption={handleBuildOption}
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
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-6">
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}
                    className="flex flex-col items-center max-w-2xl"
                  >
                    <span className="editorial-label text-[9px] text-muted-foreground mb-4">
                      Try one of these
                    </span>
                    <div className="flex flex-wrap items-center justify-center gap-2.5">
                      {EXAMPLE_PROMPTS.map((prompt) => (
                        <button
                          key={prompt}
                          onClick={() => void handleCommand(prompt)}
                          className="pointer-events-auto px-4 py-2 border border-border bg-black/60 backdrop-blur-sm font-serif text-sm text-gray-300 hover:text-white hover:border-white transition-colors duration-200"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </motion.div>
                </div>
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
              transcript={voice.transcript}
              compact={isMobile}
              settings={voiceSettings}
              onSettingsChange={updateVoiceSettings}
              onRetry={voice.retry}
              onStartListening={voice.startListening}
              onStopListening={voice.stopListening}
            />
          )}
        </div>
      </main>

      {/* Desktop — fixed, collapsible console sidebar. */}
      {!voiceMode && isDesktop && (
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
              <AlertsNotifications
                sessionId={activeDashboard?.sessionId}
                onNew={handleAlertEvent}
              />
              <ChatPanel
                sessionId={convo.sessionId}
                onCommand={handleCommand}
                isProcessing={orchestrate.isPending || streamBusy}
                messages={convo.messages}
                streamingAnswer={streamingAnswer}
                inputRef={commandInputRef}
              />
            </div>
          </aside>
        </div>
      )}
      </div>

      {/* Status bar — surfaces the keyboard shortcuts for power-user navigation. */}
      <footer className="hidden sm:flex items-center justify-between h-7 shrink-0 border-t border-border px-4 sm:px-8 bg-black/70 backdrop-blur-sm">
        <div className="flex items-center gap-5">
          <span className="editorial-label text-[9px] text-muted-foreground">Shortcuts</span>
          <span className="flex items-center gap-1.5 text-[9px] text-muted-foreground">
            <kbd className="px-1.5 py-0.5 border border-border bg-black font-mono text-gray-300 leading-none">/</kbd>
            <span>or</span>
            <kbd className="px-1.5 py-0.5 border border-border bg-black font-mono text-gray-300 leading-none">{modLabel}</kbd>
            <span>Focus command</span>
          </span>
          <span className="flex items-center gap-1.5 text-[9px] text-muted-foreground">
            <kbd className="px-1.5 py-0.5 border border-border bg-black font-mono text-gray-300 leading-none">Esc</kbd>
            <span>Toggle console</span>
          </span>
        </div>
        <span className="editorial-label text-[9px] text-muted-foreground">
          {chatOpen ? "Console Open" : "Console Collapsed"}
        </span>
      </footer>

      {/* Mobile & tablet — the console lives in a slide-up drawer, opened from a
          floating button so it never crowds the dashboard. */}
      {!voiceMode && !isDesktop && (
        <>
          {!mobileConsoleOpen && (
            <button
              onClick={() => setMobileConsoleOpen(true)}
              className="fixed bottom-5 right-5 z-30 flex items-center gap-2 px-4 py-3 bg-white text-black editorial-label text-[10px] shadow-2xl active:scale-95 transition-transform"
              aria-label="Open command console"
            >
              <Command className="w-4 h-4" strokeWidth={1.5} />
              Console
            </button>
          )}
          <AnimatePresence>
            {mobileConsoleOpen && (
              <motion.div
                key="mobile-console"
                initial={{ y: "100%" }}
                animate={{ y: 0 }}
                exit={{ y: "100%" }}
                transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                className="fixed inset-0 z-40 bg-black flex flex-col"
              >
                <ChatPanel
                  sessionId={convo.sessionId}
                  onCommand={(cmd) => {
                    setMobileConsoleOpen(false);
                    handleCommand(cmd);
                  }}
                  isProcessing={orchestrate.isPending}
                  messages={convo.messages}
                  onClose={() => setMobileConsoleOpen(false)}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}

      <NavigatorCursor
        active={navigator.active}
        status={navigator.status}
        point={navigator.point}
        caption={navigator.caption}
        title={navigator.title}
        index={navigator.index}
        total={navigator.total}
        // During a spoken walkthrough the conductor owns advancing in step with
        // narration, so hide manual prev/next; Stop still dismisses everything.
        manualControls={!voiceMode}
        onStop={() => {
          // In voice mode, also cut short the in-flight narration so dismissing
          // the cursor silences the AI too.
          if (voiceMode) voiceRef.current.cancelNarration();
          navigatorRef.current.stop();
        }}
        onNext={navigator.next}
        onPrev={navigator.prev}
      />

      <FeatureRequestModal open={showFeatureModal} onClose={() => setShowFeatureModal(false)} />

      <AdminConsoleModal open={showAdminModal} onClose={() => setShowAdminModal(false)} />

      <SavedDashboardsModal
        open={showDashboardsModal}
        onClose={() => setShowDashboardsModal(false)}
        current={activeDashboard}
        onRestore={(spec) => {
          setActiveDashboard(spec);
          pushReply(spec);
        }}
      />

      <AuditLogModal open={showAuditModal} onClose={() => setShowAuditModal(false)} />
    </div>
  );
}
