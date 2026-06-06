import React, { useState, useRef, useEffect, useCallback } from "react";
import { X, Sparkles, Loader2, Check, AlertTriangle, Trash2, Settings2, ArrowLeft } from "lucide-react";

interface FeatureRequestModalProps {
  open: boolean;
  onClose: () => void;
}

interface ManagedFeature {
  panelType: string;
  name: string;
  description: string;
  invokeExample: string;
  createdAt: string | null;
}

type View = "build" | "manage";

function formatCreatedAt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

type Stage = "planning" | "generating_skill" | "generating_panel" | "activating" | "done" | "error";

interface ProgressEvent {
  stage: Stage;
  message?: string;
  feature?: { panelType: string; featureName: string; invokeExample: string };
}

const STAGE_ORDER: Stage[] = ["planning", "generating_skill", "generating_panel", "activating", "done"];

const STAGE_LABELS: Record<Stage, string> = {
  planning: "Interpreting request",
  generating_skill: "Building data skill",
  generating_panel: "Designing panel",
  activating: "Activating capability",
  done: "Ready",
  error: "Failed",
};

const EXAMPLES = [
  "A crypto fear & greed gauge",
  "An options flow tracker for a ticker",
  "A short-squeeze risk scoreboard",
  "An earnings countdown calendar",
];

export function FeatureRequestModal({ open, onClose }: FeatureRequestModalProps) {
  const [view, setView] = useState<View>("build");
  const [description, setDescription] = useState("");
  const [isBuilding, setIsBuilding] = useState(false);
  const [currentStage, setCurrentStage] = useState<Stage | null>(null);
  const [messages, setMessages] = useState<{ stage: Stage; text: string }[]>([]);
  const [result, setResult] = useState<ProgressEvent["feature"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [features, setFeatures] = useState<ManagedFeature[]>([]);
  const [featuresLoading, setFeaturesLoading] = useState(false);
  const [featuresError, setFeaturesError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const loadFeatures = useCallback(async () => {
    setFeaturesLoading(true);
    setFeaturesError(null);
    try {
      const res = await fetch("/api/features");
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = (await res.json()) as { features?: ManagedFeature[] };
      setFeatures(data.features ?? []);
    } catch (err: any) {
      setFeaturesError(err?.message || "Couldn't load your features.");
    } finally {
      setFeaturesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && view === "manage") {
      void loadFeatures();
      setConfirmDelete(null);
    }
  }, [open, view, loadFeatures]);

  useEffect(() => {
    if (!open) {
      abortRef.current?.abort();
      setView("build");
      setDescription("");
      setIsBuilding(false);
      setCurrentStage(null);
      setMessages([]);
      setResult(null);
      setError(null);
      setConfirmDelete(null);
      setDeleting(null);
      setFeaturesError(null);
    }
  }, [open]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const handleDelete = async (panelType: string) => {
    setDeleting(panelType);
    setFeaturesError(null);
    try {
      const res = await fetch(`/api/features/${encodeURIComponent(panelType)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`Delete failed (${res.status})`);
      setFeatures((prev) => prev.filter((f) => f.panelType !== panelType));
      setConfirmDelete(null);
    } catch (err: any) {
      setFeaturesError(err?.message || "Couldn't remove that feature.");
    } finally {
      setDeleting(null);
    }
  };

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim() || isBuilding) return;

    setIsBuilding(true);
    setMessages([]);
    setResult(null);
    setError(null);
    setCurrentStage("planning");

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/feature-request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: description.trim() }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`Request failed (${res.status})`);
      }

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
          const json = line.slice(5).trim();
          if (!json) continue;
          let ev: ProgressEvent;
          try {
            ev = JSON.parse(json);
          } catch {
            continue;
          }
          handleEvent(ev);
        }
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        setError(err?.message || "Something went wrong.");
        setCurrentStage("error");
      }
    } finally {
      setIsBuilding(false);
    }
  };

  const handleEvent = (ev: ProgressEvent) => {
    setCurrentStage(ev.stage);
    if (ev.message) {
      setMessages((prev) => [...prev, { stage: ev.stage, text: ev.message! }]);
    }
    if (ev.stage === "done" && ev.feature) {
      setResult(ev.feature);
    }
    if (ev.stage === "error") {
      setError(ev.message || "Feature generation failed.");
    }
  };

  const activeIndex = currentStage ? STAGE_ORDER.indexOf(currentStage) : -1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-black border border-border flex flex-col max-h-[85vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-border shrink-0">
          <div className="flex flex-col gap-1">
            <span className="editorial-label text-[8.5px] text-muted-foreground flex items-center gap-1.5">
              <Sparkles className="w-3 h-3" strokeWidth={1.5} /> Self-Building Terminal
            </span>
            <span className="font-serif text-xl leading-none">
              {view === "build" ? "Build a Feature" : "Your Features"}
            </span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-white transition-colors">
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        <div className="flex items-center gap-1 px-6 pt-3 border-b border-border shrink-0">
          <button
            onClick={() => setView("build")}
            className={`flex items-center gap-1.5 px-3 py-2 editorial-label text-[9px] border-b-2 -mb-px transition-colors ${
              view === "build"
                ? "border-white text-white"
                : "border-transparent text-muted-foreground hover:text-white"
            }`}
          >
            <Sparkles className="w-3 h-3" strokeWidth={1.5} /> Build
          </button>
          <button
            onClick={() => setView("manage")}
            className={`flex items-center gap-1.5 px-3 py-2 editorial-label text-[9px] border-b-2 -mb-px transition-colors ${
              view === "manage"
                ? "border-white text-white"
                : "border-transparent text-muted-foreground hover:text-white"
            }`}
          >
            <Settings2 className="w-3 h-3" strokeWidth={1.5} /> Manage
          </button>
        </div>

        {view === "manage" ? (
          <div className="overflow-y-auto px-6 py-5 flex flex-col gap-4">
            {featuresError && (
              <div className="flex items-center gap-2 text-amber-400">
                <AlertTriangle className="w-3.5 h-3.5" strokeWidth={1.5} />
                <span className="text-xs">{featuresError}</span>
              </div>
            )}

            {featuresLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground py-6">
                <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} />
                <span className="text-xs font-serif">Loading your features…</span>
              </div>
            ) : features.length === 0 ? (
              <div className="flex flex-col items-start gap-3 py-6">
                <p className="text-sm text-muted-foreground leading-relaxed">
                  You haven't built any custom features yet. Switch to the Build tab to create one.
                </p>
                <button
                  onClick={() => setView("build")}
                  className="flex items-center gap-2 bg-white text-black px-4 py-2 editorial-label text-[9px] hover:bg-white/90 transition-colors"
                >
                  <Sparkles className="w-3 h-3" strokeWidth={2} /> Build a Feature
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {features.map((f) => (
                  <div key={f.panelType} className="border border-border px-4 py-3 flex flex-col gap-2">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex flex-col gap-0.5 min-w-0">
                        <span className="font-serif text-base leading-tight truncate">{f.name}</span>
                        <span className="editorial-label text-[8px] text-muted-foreground">
                          Added {formatCreatedAt(f.createdAt)}
                        </span>
                      </div>
                      {confirmDelete !== f.panelType && (
                        <button
                          onClick={() => {
                            setConfirmDelete(f.panelType);
                            setFeaturesError(null);
                          }}
                          disabled={deleting !== null}
                          className="shrink-0 flex items-center gap-1.5 text-muted-foreground hover:text-red-400 disabled:opacity-40 transition-colors"
                          aria-label={`Remove ${f.name}`}
                        >
                          <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                        </button>
                      )}
                    </div>

                    {f.description && (
                      <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">{f.description}</p>
                    )}

                    <div className="bg-white/5 border border-border px-2.5 py-1.5 font-serif text-xs text-white/90">
                      “{f.invokeExample}”
                    </div>

                    {confirmDelete === f.panelType && (
                      <div className="flex flex-col gap-2 border-t border-border pt-2.5 mt-0.5">
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          Remove <span className="text-white">{f.name}</span>? This deletes its skill and panel — it can't be undone, but you can always rebuild it.
                        </p>
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleDelete(f.panelType)}
                            disabled={deleting !== null}
                            className="flex items-center gap-1.5 bg-red-500/90 text-white px-3 py-1.5 editorial-label text-[9px] hover:bg-red-500 disabled:opacity-50 transition-colors"
                          >
                            {deleting === f.panelType ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} /> Removing
                              </>
                            ) : (
                              <>
                                <Trash2 className="w-3 h-3" strokeWidth={2} /> Remove
                              </>
                            )}
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            disabled={deleting !== null}
                            className="flex items-center gap-1.5 border border-border px-3 py-1.5 editorial-label text-[9px] text-muted-foreground hover:text-white hover:border-white/40 disabled:opacity-50 transition-colors"
                          >
                            <ArrowLeft className="w-3 h-3" strokeWidth={2} /> Keep
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
        <div className="overflow-y-auto px-6 py-5 flex flex-col gap-5">
          {!result && !error && (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <label className="flex flex-col gap-2">
                <span className="editorial-label text-[8.5px] text-muted-foreground">
                  Describe the capability you want
                </span>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={isBuilding}
                  rows={3}
                  autoFocus
                  placeholder="e.g. A panel that scores meme-stock momentum across Reddit-favorite tickers"
                  className="w-full bg-transparent border border-border px-3 py-2.5 text-sm font-serif text-white placeholder:text-muted-foreground/60 focus:outline-none focus:border-white transition-colors resize-none"
                />
              </label>

              {!isBuilding && (
                <div className="flex flex-wrap gap-1.5">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex}
                      type="button"
                      onClick={() => setDescription(ex)}
                      className="text-[10px] text-muted-foreground hover:text-white border border-border hover:border-white/40 px-2 py-1 transition-colors"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              )}

              <button
                type="submit"
                disabled={!description.trim() || isBuilding}
                className="self-start flex items-center gap-2 bg-white text-black px-4 py-2 editorial-label text-[9px] disabled:opacity-40 hover:bg-white/90 transition-colors"
              >
                {isBuilding ? (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} /> Building
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3 h-3" strokeWidth={2} /> Build Feature
                  </>
                )}
              </button>
            </form>
          )}

          {(isBuilding || messages.length > 0) && !result && !error && (
            <div className="flex flex-col gap-2.5 border-t border-border pt-4">
              {STAGE_ORDER.slice(0, 4).map((stage, i) => {
                const reached = activeIndex >= i || activeIndex === -1;
                const isActive = currentStage === stage;
                const isDone = activeIndex > i || currentStage === "done";
                return (
                  <div key={stage} className="flex items-center gap-2.5">
                    <span className="w-3.5 flex items-center justify-center">
                      {isDone ? (
                        <Check className="w-3 h-3 text-emerald-400" strokeWidth={2} />
                      ) : isActive ? (
                        <Loader2 className="w-3 h-3 animate-spin text-white" strokeWidth={2} />
                      ) : (
                        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40" />
                      )}
                    </span>
                    <span
                      className={`text-xs font-serif ${
                        isActive ? "text-white" : isDone ? "text-muted-foreground" : "text-muted-foreground/50"
                      }`}
                    >
                      {STAGE_LABELS[stage]}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {result && (
            <div className="flex flex-col gap-4 items-start">
              <div className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-400" strokeWidth={2} />
                <span className="font-serif text-lg">{result.featureName} is live</span>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Your new capability is active — no restart needed. Try it now by typing this in the chat:
              </p>
              <div className="w-full bg-white/5 border border-border px-3 py-2.5 font-serif text-sm text-white">
                “{result.invokeExample}”
              </div>
              <div className="flex gap-2">
                <button
                  onClick={onClose}
                  className="bg-white text-black px-4 py-2 editorial-label text-[9px] hover:bg-white/90 transition-colors"
                >
                  Done
                </button>
                <button
                  onClick={() => {
                    setResult(null);
                    setDescription("");
                    setMessages([]);
                    setCurrentStage(null);
                  }}
                  className="border border-border px-4 py-2 editorial-label text-[9px] text-muted-foreground hover:text-white hover:border-white/40 transition-colors"
                >
                  Build Another
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="flex flex-col gap-4 items-start">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" strokeWidth={1.5} />
                <span className="font-serif text-lg">Couldn't build that</span>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">{error}</p>
              <button
                onClick={() => {
                  setError(null);
                  setCurrentStage(null);
                  setMessages([]);
                }}
                className="bg-white text-black px-4 py-2 editorial-label text-[9px] hover:bg-white/90 transition-colors"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
        )}
      </div>
    </div>
  );
}
