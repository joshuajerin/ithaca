import React, { useCallback, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { DashboardSpec, PanelLayout } from "@workspace/api-client-react";
import { PanelContainer } from "./PanelContainer";
import { resolvePanelLayouts, GRID_COLUMNS } from "@/lib/layout";

interface DashboardProps {
  dashboard: DashboardSpec;
  onPanelRefined: (updatedPanel: any) => void;
  onPanelResized?: (panelId: string, size: { w: number; h: number }) => void;
  highlightedPanelId?: string | null;
}

// Grid metrics — must mirror the CSS below. gap-6 = 1.5rem = 24px,
// gridAutoRows is a fixed 120px band.
const GRID_GAP = 24;
const ROW_HEIGHT = 120;
const MIN_W = 2;
const MIN_H = 2;

type ResizeMode = "right" | "bottom" | "both";

interface DragState {
  id: string;
  mode: ResizeMode;
  startX: number;
  startY: number;
  startW: number;
  startH: number;
  // Leftmost column of the panel — caps how wide it can grow.
  x: number;
  unitX: number;
  unitY: number;
  curW: number;
  curH: number;
}

/**
 * Effective grid width for the current viewport. On phones we collapse to a
 * single stacked column; on tablets / narrow desktops we halve the grid so wide
 * panels are not crammed into a raw 12-column layout. The same reserve-then-reflow
 * algorithm in `resolvePanelLayouts` adapts to whatever column count we return.
 */
function useResponsiveColumns(): number {
  const getColumns = React.useCallback(() => {
    if (typeof window === "undefined") return GRID_COLUMNS;
    const w = window.innerWidth;
    if (w < 768) return 1;
    if (w < 1280) return 6;
    return GRID_COLUMNS;
  }, []);

  const [columns, setColumns] = React.useState<number>(getColumns);

  React.useEffect(() => {
    const onResize = () => setColumns(getColumns());
    window.addEventListener("resize", onResize);
    onResize();
    return () => window.removeEventListener("resize", onResize);
  }, [getColumns]);

  return columns;
}

export function Dashboard({
  dashboard,
  onPanelRefined,
  onPanelResized,
  highlightedPanelId,
}: DashboardProps) {
  const columns = useResponsiveColumns();
  const gridRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  // Live preview of the panel currently being resized. Only the dragged panel
  // is overridden — every other panel keeps its committed layout.
  const [draft, setDraft] = useState<{ id: string; w: number; h: number } | null>(null);
  const resizable = !!onPanelResized;

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    e.preventDefault();
    const dx = e.clientX - d.startX;
    const dy = e.clientY - d.startY;

    let w = d.startW;
    let h = d.startH;
    if (d.mode === "right" || d.mode === "both") {
      const deltaW = Math.round(dx / d.unitX);
      // Cap to the columns remaining to the right of this panel. On very narrow
      // grids that maximum can be below MIN_W, so floor the minimum accordingly.
      const maxW = columns - d.x;
      w = Math.max(Math.min(MIN_W, maxW), Math.min(maxW, d.startW + deltaW));
    }
    if (d.mode === "bottom" || d.mode === "both") {
      const deltaH = Math.round(dy / d.unitY);
      h = Math.max(MIN_H, d.startH + deltaH);
    }

    if (w !== d.curW || h !== d.curH) {
      d.curW = w;
      d.curH = h;
      setDraft({ id: d.id, w, h });
    }
  }, [columns]);

  const endDrag = useCallback(
    (e: React.PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      try {
        (e.target as Element).releasePointerCapture(e.pointerId);
      } catch {
        /* pointer may already be released */
      }
      dragRef.current = null;
      setDraft(null);
      if (d.curW !== d.startW || d.curH !== d.startH) {
        onPanelResized?.(d.id, { w: d.curW, h: d.curH });
      }
    },
    [onPanelResized],
  );

  const beginResize = useCallback(
    (e: React.PointerEvent, layout: PanelLayout, id: string, mode: ResizeMode) => {
      if (!resizable) return;
      const grid = gridRef.current;
      if (!grid) return;
      e.preventDefault();
      e.stopPropagation();
      const rect = grid.getBoundingClientRect();
      const col = (rect.width - GRID_GAP * (columns - 1)) / columns;
      dragRef.current = {
        id,
        mode,
        startX: e.clientX,
        startY: e.clientY,
        startW: layout.w,
        startH: layout.h,
        x: layout.x,
        unitX: col + GRID_GAP,
        unitY: ROW_HEIGHT + GRID_GAP,
        curW: layout.w,
        curH: layout.h,
      };
      setDraft({ id, w: layout.w, h: layout.h });
      try {
        (e.target as Element).setPointerCapture(e.pointerId);
      } catch {
        /* capture is best-effort */
      }
    },
    [resizable, columns],
  );

  if (!dashboard.panels || dashboard.panels.length === 0) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center gap-2 py-24 text-center">
        <span className="font-serif text-xl text-muted-foreground">No active panels</span>
        <span className="editorial-label text-[9px] text-muted-foreground">Enter a command to synthesize data</span>
      </div>
    );
  }

  // Resolve any overlapping / off-grid coordinates the AI may have emitted so
  // no two panels ever stack on top of each other. The column count adapts to
  // the viewport so wide panels collapse gracefully on smaller windows.
  const panels = resolvePanelLayouts(dashboard.panels, columns);

  // Row height is ~100px. We use CSS Grid where each unit of height represents roughly that.
  return (
    <div
      ref={gridRef}
      className={`grid gap-6 w-full ${draft ? "select-none" : ""}`}
      style={{
        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
        gridAutoRows: "120px",
      }}
    >
      <AnimatePresence>
        {panels.map((panel) => {
          const isDragging = draft?.id === panel.id;
          const w = isDragging ? draft!.w : panel.layout.w;
          const h = isDragging ? draft!.h : panel.layout.h;
          return (
            <motion.div
              key={panel.id}
              data-panel-id={panel.id}
              layout={!isDragging}
              initial={{ opacity: 0, y: 14, scale: 0.98, filter: "blur(2px)" }}
              animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
              exit={{ opacity: 0, scale: 0.97, filter: "blur(2px)" }}
              transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
              className="min-h-0 relative group/panel"
              style={{
                gridColumnStart: panel.layout.x + 1,
                gridColumnEnd: `span ${w}`,
                gridRowStart: panel.layout.y + 1,
                gridRowEnd: `span ${h}`,
                zIndex: isDragging ? 20 : undefined,
              }}
            >
              <PanelContainer
                panel={panel}
                sessionId={dashboard.sessionId}
                onRefined={onPanelRefined}
                highlighted={highlightedPanelId === panel.id}
              />

              {resizable && (
                <>
                  {/* Right edge — adjust width */}
                  <div
                    role="separator"
                    aria-label="Resize panel width"
                    onPointerDown={(e) => beginResize(e, panel.layout, panel.id, "right")}
                    onPointerMove={onPointerMove}
                    onPointerUp={endDrag}
                    onPointerCancel={endDrag}
                    className={`absolute top-3 bottom-6 -right-1 w-2 cursor-ew-resize touch-none transition-opacity ${
                      isDragging ? "opacity-100" : "opacity-0 group-hover/panel:opacity-100"
                    }`}
                  >
                    <span className="absolute top-1/2 right-0.5 -translate-y-1/2 h-8 w-[2px] rounded-full bg-white/60" />
                  </div>

                  {/* Bottom edge — adjust height */}
                  <div
                    role="separator"
                    aria-label="Resize panel height"
                    onPointerDown={(e) => beginResize(e, panel.layout, panel.id, "bottom")}
                    onPointerMove={onPointerMove}
                    onPointerUp={endDrag}
                    onPointerCancel={endDrag}
                    className={`absolute left-3 right-6 -bottom-1 h-2 cursor-ns-resize touch-none transition-opacity ${
                      isDragging ? "opacity-100" : "opacity-0 group-hover/panel:opacity-100"
                    }`}
                  >
                    <span className="absolute left-1/2 bottom-0.5 -translate-x-1/2 w-8 h-[2px] rounded-full bg-white/60" />
                  </div>

                  {/* Bottom-right corner — adjust both */}
                  <div
                    role="separator"
                    aria-label="Resize panel"
                    onPointerDown={(e) => beginResize(e, panel.layout, panel.id, "both")}
                    onPointerMove={onPointerMove}
                    onPointerUp={endDrag}
                    onPointerCancel={endDrag}
                    title="Drag to resize"
                    className={`absolute -bottom-1 -right-1 w-4 h-4 cursor-nwse-resize touch-none transition-opacity ${
                      isDragging ? "opacity-100" : "opacity-0 group-hover/panel:opacity-100"
                    }`}
                  >
                    <span className="absolute bottom-1 right-1 w-2 h-2 border-r-2 border-b-2 border-white/70" />
                  </div>
                </>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
