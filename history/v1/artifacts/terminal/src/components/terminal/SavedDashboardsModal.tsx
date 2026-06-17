import React, { useEffect, useState } from "react";
import { X, LayoutGrid, Loader2, Save, Trash2, AlertTriangle, Check } from "lucide-react";
import {
  useListSavedDashboards,
  saveDashboard,
  restoreDashboard,
  deleteSavedDashboard,
} from "@workspace/api-client-react";
import type { DashboardSpec, SavedDashboardMeta } from "@workspace/api-client-react";

interface SavedDashboardsModalProps {
  open: boolean;
  onClose: () => void;
  current: DashboardSpec | null;
  onRestore: (spec: DashboardSpec) => void;
}

function formatWhen(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SavedDashboardsModal({ open, onClose, current, onRestore }: SavedDashboardsModalProps) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  const list = useListSavedDashboards();
  const dashboards: SavedDashboardMeta[] = list.data?.dashboards ?? [];

  useEffect(() => {
    if (open) {
      void list.refetch();
    } else {
      setName("");
      setSaving(false);
      setBusyId(null);
      setError(null);
      setJustSaved(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const panelCount = current?.panels.length ?? 0;
  const canSave = panelCount > 0 && name.trim().length > 0 && !saving;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSave || !current) return;
    setSaving(true);
    setError(null);
    try {
      await saveDashboard({
        name: name.trim(),
        summary: current.summary,
        panels: current.panels,
      });
      setName("");
      setJustSaved(true);
      window.setTimeout(() => setJustSaved(false), 2000);
      await list.refetch();
    } catch (err: any) {
      setError(err?.message || "Could not save this dashboard.");
    } finally {
      setSaving(false);
    }
  };

  const handleRestore = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      const spec = await restoreDashboard(id);
      onRestore(spec);
      onClose();
    } catch (err: any) {
      setError(err?.message || "Could not restore that dashboard.");
      setBusyId(null);
    }
  };

  const handleDelete = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      await deleteSavedDashboard(id);
      await list.refetch();
    } catch (err: any) {
      setError(err?.message || "Could not delete that dashboard.");
    } finally {
      setBusyId(null);
    }
  };

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
              <LayoutGrid className="w-3 h-3" strokeWidth={1.5} /> Layouts
            </span>
            <span className="font-serif text-xl leading-none">Saved Dashboards</span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-white transition-colors">
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-5 flex flex-col gap-5">
          <form onSubmit={handleSave} className="flex flex-col gap-3">
            <label className="flex flex-col gap-2">
              <span className="editorial-label text-[8.5px] text-muted-foreground">
                Save the current dashboard
              </span>
              <div className="flex gap-2">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={saving || panelCount === 0}
                  placeholder={panelCount === 0 ? "No panels to save yet" : "Name this layout…"}
                  className="flex-1 bg-transparent border border-border px-3 py-2.5 text-sm font-serif text-white placeholder:text-muted-foreground/60 focus:outline-none focus:border-white transition-colors"
                />
                <button
                  type="submit"
                  disabled={!canSave}
                  className="flex items-center gap-2 bg-white text-black px-4 editorial-label text-[9px] disabled:opacity-40 hover:bg-white/90 transition-colors"
                >
                  {saving ? (
                    <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} />
                  ) : justSaved ? (
                    <Check className="w-3 h-3" strokeWidth={2} />
                  ) : (
                    <Save className="w-3 h-3" strokeWidth={2} />
                  )}
                  {justSaved ? "Saved" : "Save"}
                </button>
              </div>
            </label>
            {panelCount > 0 && (
              <span className="text-[10px] text-muted-foreground">
                {panelCount} panel{panelCount === 1 ? "" : "s"} on screen. Reusing a name overwrites that layout.
              </span>
            )}
          </form>

          {error && (
            <div className="flex items-center gap-2 text-amber-400 text-xs border border-amber-400/30 px-3 py-2">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
              <span>{error}</span>
            </div>
          )}

          <div className="flex flex-col gap-2 border-t border-border pt-4">
            <span className="editorial-label text-[8.5px] text-muted-foreground">
              Your saved layouts
            </span>

            {list.isLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground text-xs py-6 justify-center">
                <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} /> Loading
              </div>
            ) : dashboards.length === 0 ? (
              <p className="text-sm text-muted-foreground/70 py-6 text-center font-serif">
                No saved dashboards yet. Compose a view and save it above.
              </p>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {dashboards.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 py-3 group">
                    <div className="flex-1 min-w-0">
                      <div className="font-serif text-sm text-white truncate">{d.name}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        {d.panelCount} panel{d.panelCount === 1 ? "" : "s"}
                        {formatWhen(d.updatedAt) ? ` · ${formatWhen(d.updatedAt)}` : ""}
                      </div>
                    </div>
                    <button
                      onClick={() => handleRestore(d.id)}
                      disabled={busyId === d.id}
                      className="flex items-center gap-1.5 bg-white text-black px-3 py-1.5 editorial-label text-[9px] disabled:opacity-40 hover:bg-white/90 transition-colors"
                    >
                      {busyId === d.id ? (
                        <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} />
                      ) : (
                        "Restore"
                      )}
                    </button>
                    <button
                      onClick={() => handleDelete(d.id)}
                      disabled={busyId === d.id}
                      aria-label={`Delete ${d.name}`}
                      className="text-muted-foreground hover:text-amber-400 transition-colors disabled:opacity-40 p-1"
                    >
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
