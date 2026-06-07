import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Slider } from "@/components/ui/slider";

export function OrderBookPanel({ data }: { data: any }) {
  const frames: any[] = Array.isArray(data.frames) ? data.frames : [];
  const hasReplay = frames.length > 1;
  const events: any[] = Array.isArray(data.events) ? data.events : [];

  const liveIndex = hasReplay ? frames.length - 1 : 0;
  const initialIndex =
    typeof data.selectedIndex === "number" ? data.selectedIndex : liveIndex;
  const [index, setIndex] = React.useState(initialIndex);

  React.useEffect(() => {
    setIndex(
      typeof data.selectedIndex === "number" ? data.selectedIndex : liveIndex,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.symbol, frames.length]);

  const frame = hasReplay ? frames[Math.min(index, frames.length - 1)] : data;
  const isLive = !hasReplay || index >= liveIndex;
  const currentTime: string | undefined = frame?.time ?? data.timestamp;

  // Events at or before the current frame are "passed" — highlight them.
  const currentPos = hasReplay ? index / Math.max(1, frames.length - 1) : 1;

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest">
            {data.symbol} · Order Book
          </div>
          <div className="text-xl font-bold font-mono">
            ${frame.lastPrice.toFixed(2)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest">
            Spread
          </div>
          <div className="text-sm font-mono text-white">
            ${frame.spread.toFixed(2)}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 flex-1 min-h-0">
        <div className="flex flex-col min-h-0">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1 shrink-0">
            Bids
          </div>
          <div className="flex-1 min-h-0 overflow-hidden space-y-0.5">
            {frame.bids.map((level: any, i: any) => (
              <div
                key={i}
                className="relative flex items-center justify-between px-1.5 py-0.5 text-[11px] font-mono overflow-hidden"
              >
                <div
                  className="absolute inset-0 bg-white/8"
                  style={{ width: `${level.depth * 100}%` }}
                />
                <span className="relative z-10 text-white font-bold">
                  ${level.price.toFixed(2)}
                </span>
                <span className="relative z-10 text-muted-foreground">
                  {level.size.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col min-h-0">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1 shrink-0">
            Asks
          </div>
          <div className="flex-1 min-h-0 overflow-hidden space-y-0.5">
            {frame.asks.map((level: any, i: any) => (
              <div
                key={i}
                className="relative flex items-center justify-between px-1.5 py-0.5 text-[11px] font-mono overflow-hidden"
              >
                <div
                  className="absolute right-0 top-0 bottom-0 bg-white/5"
                  style={{ width: `${level.depth * 100}%` }}
                />
                <span className="relative z-10 text-muted-foreground">
                  ${level.price.toFixed(2)}
                </span>
                <span className="relative z-10 text-white/70">
                  {level.size.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-border pt-2">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Recent Tape
          </div>
          {currentTime && (
            <div className="flex items-center gap-1.5">
              {isLive ? (
                <span className="flex items-center gap-1 text-[9px] uppercase tracking-wider text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Live
                </span>
              ) : (
                <span className="text-[9px] uppercase tracking-wider text-amber-400">
                  Replay
                </span>
              )}
              <span className="font-mono text-[10px] text-white tabular-nums">
                {currentTime}
              </span>
            </div>
          )}
        </div>
        <ScrollArea className="h-[80px]">
          <div className="space-y-0.5">
            {frame.tape.map((print: any, i: any) => {
              const flagged = print.isBlock || print.isSweep;
              return (
                <div
                  key={i}
                  className={`relative flex items-center justify-between text-[10px] font-mono gap-2 rounded-sm ${
                    print.isBlock
                      ? "bg-amber-400/15 ring-1 ring-amber-400/30 px-1"
                      : print.isSweep
                        ? "bg-sky-400/15 ring-1 ring-sky-400/30 px-1"
                        : ""
                  }`}
                >
                  <span className="text-muted-foreground w-16 shrink-0">
                    {print.time}
                  </span>
                  <span
                    className={`font-bold w-14 shrink-0 ${
                      print.side === "buy" ? "text-white" : "text-gray-500"
                    }`}
                  >
                    ${print.price.toFixed(2)}
                  </span>
                  <span className="text-muted-foreground w-14 shrink-0 text-right">
                    {print.size.toLocaleString()}
                  </span>
                  {flagged ? (
                    <span
                      className={`w-10 shrink-0 text-right uppercase text-[8px] font-bold tracking-wider ${
                        print.isBlock ? "text-amber-400" : "text-sky-400"
                      }`}
                    >
                      {print.isBlock ? "block" : "sweep"}
                    </span>
                  ) : (
                    <span
                      className={`w-10 shrink-0 text-right uppercase text-[9px] tracking-wider ${
                        print.side === "buy" ? "text-white/60" : "text-gray-600"
                      }`}
                    >
                      {print.side}
                    </span>
                  )}
                  <span className="text-muted-foreground/50 text-[9px] shrink-0">
                    {print.venue}
                  </span>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </div>

      {hasReplay && (
        <div className="shrink-0 border-t border-border pt-2.5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Depth Replay
            </span>
            <div className="flex items-center gap-2.5 text-[9px] uppercase tracking-wider">
              <span className="flex items-center gap-1 text-amber-400">
                <span className="h-1.5 w-1.5 rounded-sm bg-amber-400" /> Block
              </span>
              <span className="flex items-center gap-1 text-sky-400">
                <span className="h-1.5 w-1.5 rounded-sm bg-sky-400" /> Sweep
              </span>
            </div>
          </div>

          <div className="relative">
            {/* Event markers along the timeline track */}
            <div className="absolute left-0 right-0 top-0 h-1.5 pointer-events-none">
              {events.map((ev: any, i: number) => {
                const pos = Math.max(0, Math.min(1, ev.pos ?? 0));
                const passed = pos <= currentPos + 1e-6;
                return (
                  <div
                    key={i}
                    title={`${ev.type === "block" ? "Block" : "Sweep"} · ${ev.time} · ${ev.side} ${Number(ev.size).toLocaleString()} @ $${Number(ev.price).toFixed(2)}`}
                    className={`absolute -top-1 h-3.5 w-[3px] rounded-full transition-opacity ${
                      ev.type === "block" ? "bg-amber-400" : "bg-sky-400"
                    } ${passed ? "opacity-100" : "opacity-25"}`}
                    style={{ left: `calc(${pos * 100}% - 1.5px)` }}
                  />
                );
              })}
            </div>
            <Slider
              value={[index]}
              min={0}
              max={frames.length - 1}
              step={1}
              onValueChange={(v) => setIndex(v[0])}
              className="relative z-10"
            />
          </div>

          <div className="flex items-center justify-between mt-1.5 text-[9px] font-mono text-muted-foreground tabular-nums">
            <span>{data.sessionStart ?? frames[0]?.time}</span>
            <button
              type="button"
              onClick={() => setIndex(liveIndex)}
              disabled={isLive}
              className={`uppercase tracking-wider transition-colors ${
                isLive
                  ? "text-muted-foreground/40 cursor-default"
                  : "text-emerald-400 hover:text-emerald-300"
              }`}
            >
              Jump to live
            </button>
            <span>{data.sessionEnd ?? frames[frames.length - 1]?.time}</span>
          </div>
        </div>
      )}
    </div>
  );
}
