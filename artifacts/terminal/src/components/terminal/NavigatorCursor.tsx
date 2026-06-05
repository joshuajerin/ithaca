import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import type { NavigatorPoint, NavigatorStatus } from "@/hooks/useNavigator";

interface NavigatorCursorProps {
  active: boolean;
  status: NavigatorStatus;
  point: NavigatorPoint | null;
  caption: string;
  title: string;
  index: number;
  total: number;
  onStop: () => void;
  onNext: () => void;
  onPrev: () => void;
}

const CAPTION_W = 264;

export function NavigatorCursor({
  active,
  status,
  point,
  caption,
  title,
  index,
  total,
  onStop,
  onNext,
  onPrev,
}: NavigatorCursorProps) {
  const [vw, setVw] = useState(() => (typeof window !== "undefined" ? window.innerWidth : 1280));
  const [vh, setVh] = useState(() => (typeof window !== "undefined" ? window.innerHeight : 720));

  useEffect(() => {
    const onResize = () => {
      setVw(window.innerWidth);
      setVh(window.innerHeight);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  if (!active) return null;

  // Flip the caption to the cursor's left when it would overflow the viewport,
  // and above when near the bottom — so it always stays fully on screen.
  const flipX = point ? point.x + 28 + CAPTION_W > vw : false;
  const flipY = point ? point.y + 150 > vh : false;
  const captionX = flipX ? -CAPTION_W - 18 : 26;
  const captionY = flipY ? -132 : 18;

  return (
    <>
      {/* Cursor + caption overlay. Never intercepts clicks so manual use is unaffected. */}
      <div className="fixed inset-0 z-50 pointer-events-none overflow-hidden">
        <AnimatePresence>
          {point && (
            <motion.div
              key="nav-cursor"
              initial={{ x: point.x, y: point.y, opacity: 0, scale: 0.6 }}
              animate={{ x: point.x, y: point.y, opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.6 }}
              transition={{
                x: { type: "spring", stiffness: 90, damping: 18, mass: 0.9 },
                y: { type: "spring", stiffness: 90, damping: 18, mass: 0.9 },
                opacity: { duration: 0.3 },
                scale: { duration: 0.3 },
              }}
              className="absolute top-0 left-0"
              style={{ willChange: "transform" }}
            >
              {/* Soft halo so the cursor reads against any panel. */}
              <motion.div
                aria-hidden
                className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full"
                style={{
                  width: 38,
                  height: 38,
                  background: "radial-gradient(circle, rgba(255,255,255,0.28) 0%, rgba(255,255,255,0) 70%)",
                }}
                animate={{ scale: status === "reading" ? [1, 1.25, 1] : 1 }}
                transition={{ duration: 1.8, repeat: status === "reading" ? Infinity : 0, ease: "easeInOut" }}
              />
              {/* The pointer itself, tip anchored at the target point. */}
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                className="relative -translate-x-[3px] -translate-y-[3px] drop-shadow-[0_2px_6px_rgba(0,0,0,0.9)]"
              >
                <path
                  d="M5 3L19 12L12 13L9 20L5 3Z"
                  fill="white"
                  stroke="black"
                  strokeWidth="1.25"
                  strokeLinejoin="round"
                />
              </svg>

              {/* Caption card, offset from the cursor and kept on screen. */}
              <AnimatePresence mode="wait">
                {caption && status === "reading" && (
                  <motion.div
                    key={`cap-${index}`}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                    className="absolute bg-black border border-white/80 shadow-[0_0_24px_rgba(255,255,255,0.18)]"
                    style={{ left: captionX, top: captionY, width: CAPTION_W }}
                  >
                    <div className="flex items-center justify-between px-3 pt-2 pb-1.5 border-b border-border">
                      <span className="editorial-label text-[8px] text-muted-foreground">
                        AI Navigator
                      </span>
                      <span className="editorial-label text-[8px] text-muted-foreground nums-tabular">
                        {index} / {total}
                      </span>
                    </div>
                    <p className="px-3 py-2.5 font-serif text-[13px] leading-snug text-white">
                      {caption}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Control bar — the only interactive part of the navigator. */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 pointer-events-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 12 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="flex items-center gap-3 bg-black/90 backdrop-blur-sm border border-border px-3 py-2 shadow-[0_8px_40px_rgba(0,0,0,0.6)]"
        >
          <div className="flex flex-col pr-1 max-w-[180px]">
            <span className="editorial-label text-[8px] text-muted-foreground">Navigating</span>
            <span className="font-serif text-sm leading-tight truncate">{title}</span>
          </div>
          <div className="h-7 w-px bg-border" />
          <button
            onClick={onPrev}
            disabled={index <= 1}
            aria-label="Previous stop"
            className="text-muted-foreground hover:text-white disabled:opacity-30 disabled:hover:text-muted-foreground transition-colors p-1"
          >
            <ChevronLeft className="w-4 h-4" strokeWidth={1.5} />
          </button>
          <span className="editorial-label text-[9px] text-muted-foreground nums-tabular w-9 text-center">
            {index} / {total}
          </span>
          <button
            onClick={onNext}
            aria-label="Next stop"
            className="text-muted-foreground hover:text-white transition-colors p-1"
          >
            <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
          </button>
          <div className="h-7 w-px bg-border" />
          <button
            onClick={onStop}
            className="flex items-center gap-1.5 px-2.5 py-1.5 editorial-label text-[9px] border border-border bg-black text-white hover:border-white transition-colors"
          >
            <X className="w-3 h-3" strokeWidth={1.5} />
            Stop
          </button>
        </motion.div>
      </div>
    </>
  );
}
