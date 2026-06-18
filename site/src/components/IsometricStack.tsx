import { motion, useTransform } from "framer-motion";
import type { MotionValue } from "framer-motion";

/* --------------------------------------------------------------------------
 * The signature visual: three clean floating isometric slabs representing the
 * platform's three layers. Pure CSS 3D transforms — no WebGL.
 *
 *   Data layer     (top)    — vetted market data the agent reasons over
 *   Deploy layer   (middle) — declarative specs run on trusted infra
 *   Observe layer  (bottom) — the replayable, audited event log / glass box
 *
 * Controlled by scroll (or static, when `idle`):
 *   • `separation` (0..1): slabs sit stacked tight, then spread apart.
 *   • `focus` per layer (0..1): active layer shown; others REMOVED (opacity 0).
 * ------------------------------------------------------------------------ */

const ZNEAR = { top: 18, mid: 0, bot: -18 } as const;
const ZFAR = { top: 200, mid: 0, bot: -200 } as const;

type Focus = {
  top: MotionValue<number>;
  mid: MotionValue<number>;
  bot: MotionValue<number>;
};

export default function IsometricStack({
  focus,
  separation,
  idle = false,
}: {
  focus: Focus;
  separation: MotionValue<number>;
  idle?: boolean;
}) {
  return (
    <motion.div
      initial={idle ? { opacity: 0, y: 36 } : false}
      whileInView={idle ? { opacity: 1, y: 0 } : undefined}
      viewport={idle ? { once: true, margin: "-15%" } : undefined}
      transition={idle ? { duration: 1, ease: [0.22, 1, 0.36, 1] } : undefined}
      className="relative mx-auto w-full max-w-[600px]"
    >
      <EdgeLabel text="DATA LAYER" side="right" top="14%" focus={focus.top} />
      <EdgeLabel text="DEPLOY LAYER" side="left" top="50%" focus={focus.mid} />
      <EdgeLabel text="OBSERVE LAYER" side="right" top="86%" focus={focus.bot} />

      <div
        className="relative mx-auto"
        style={{ perspective: "1700px", perspectiveOrigin: "50% 44%" }}
      >
        <div
          className="preserve-3d relative mx-auto aspect-[1.32/1] w-full max-w-[520px]"
          style={{ transform: "rotateX(54deg) rotateZ(-45deg)" }}
        >
          {/* BOTTOM — observe / event-log: green dots moving through circuit paths */}
          <Plane zNear={ZNEAR.bot} zFar={ZFAR.bot} separation={separation} focus={focus.bot}>
            <div className="absolute inset-0 rounded-[30px] border border-olive/30 bg-gradient-to-br from-[#f0f4e8] to-[#e8efd7] shadow-[0_30px_70px_-28px_rgba(44,58,10,0.4)]" />
            <ObserveDots />
            <Highlight />
          </Plane>

          {/* MIDDLE — deploy / trusted infra */}
          <Plane zNear={ZNEAR.mid} zFar={ZFAR.mid} separation={separation} focus={focus.mid}>
            <div className="absolute inset-0 rounded-[30px] border border-line-strong bg-gradient-to-br from-cream to-sand-2 shadow-[0_34px_70px_-30px_rgba(24,23,15,0.42)]" />
            <PipeBars />
            <Highlight />
          </Plane>

          {/* TOP — data / the sources, carries the glowing orb */}
          <Plane zNear={ZNEAR.top} zFar={ZFAR.top} separation={separation} focus={focus.top}>
            <div className="absolute inset-0 rounded-[30px] border border-gold/40 bg-gradient-to-br from-[#f6ead0] to-sand shadow-[0_40px_90px_-32px_rgba(91,75,36,0.5)]" />
            <CellCluster />
            <Highlight />
          </Plane>
        </div>

        {/* soft ground/contact shadow to anchor the floating stack */}
        <div className="pointer-events-none absolute left-1/2 top-[64%] h-24 w-3/4 -translate-x-1/2 rounded-[50%] bg-[radial-gradient(ellipse_at_center,rgba(24,23,15,0.16),transparent_70%)] blur-2xl" />
      </div>
    </motion.div>
  );
}

/* A single floating plane. translateZ interpolates near→far via `separation`;
   `focus` fully shows/hides it (others are removed, not dimmed). */
function Plane({
  children,
  zNear,
  zFar,
  separation,
  focus,
}: {
  children: React.ReactNode;
  zNear: number;
  zFar: number;
  separation: MotionValue<number>;
  focus: MotionValue<number>;
}) {
  const baseZ = useTransform(separation, [0, 1], [zNear, zFar]);
  const lift = useTransform(focus, [0, 1], [0, 22]);
  const scale = useTransform(focus, [0, 1], [0.99, 1.03]);
  const transform = useTransform(
    [baseZ, lift, scale] as MotionValue<number>[],
    ([b, l, s]: number[]) => `translateZ(${b + l}px) scale(${s})`,
  );
  const opacity = useTransform(focus, [0, 0.55, 1], [0, 0.85, 1]);

  return (
    <motion.div className="preserve-3d absolute inset-0" style={{ transform, opacity }}>
      {children}
    </motion.div>
  );
}

/* Thin glossy top-edge highlight to make each slab read as a clean panel. */
function Highlight() {
  return (
    <div className="pointer-events-none absolute inset-0 rounded-[30px] bg-gradient-to-br from-white/45 via-transparent to-transparent" />
  );
}

/* DATA — pulsing table rows (market data ticking in) */
function CellCluster() {
  const rows = [
    { label: "NVDA", val: "+2.41%", w: 82, accent: true },
    { label: "AAPL", val: "+0.87%", w: 62, accent: false },
    { label: "MSFT", val: "-0.34%", w: 71, accent: false },
    { label: "AMZN", val: "+1.12%", w: 55, accent: false },
  ];
  return (
    <div className="absolute inset-[13%] flex flex-col gap-[8%]">
      {rows.map((r, i) => (
        <div
          key={r.label}
          className="cell-pulse flex items-center gap-[6%] rounded-[6px] border bg-white/60 px-[8%] py-[4%]"
          style={{
            borderColor: r.accent ? "rgba(239,159,42,0.45)" : "rgba(221,208,184,0.6)",
            "--dur": `${1.8 + i * 0.55}s`,
            "--del": `${i * 0.3}s`,
          } as React.CSSProperties}
        >
          <span className="flex-1 font-mono text-[9px] font-semibold uppercase tracking-widest text-ink/70">{r.label}</span>
          <span
            className="h-[6px] rounded-full bg-gradient-to-r from-gold/60 to-gold/20"
            style={{ width: `${r.w}%` }}
          />
          <span className={`font-mono text-[8px] font-bold ${r.val.startsWith("+") ? "text-olive" : "text-red-400"}`}>
            {r.val}
          </span>
        </div>
      ))}
    </div>
  );
}

/* DEPLOY — animated live equity/deployment bars (a lively mini-dashboard) */
function PipeBars() {
  // Heights and animation params for each bar column
  const bars = [
    { h: 55, peak: 0.78, dur: "2.1s", del: "0s",    col: "rgba(72,92,17,0.55)" },
    { h: 72, peak: 1.18, dur: "1.7s", del: "0.25s",  col: "rgba(72,92,17,0.75)" },
    { h: 45, peak: 0.62, dur: "2.4s", del: "0.1s",   col: "rgba(72,92,17,0.45)" },
    { h: 88, peak: 1.08, dur: "1.9s", del: "0.4s",   col: "rgba(239,159,42,0.7)" },
    { h: 60, peak: 0.85, dur: "2.2s", del: "0.15s",  col: "rgba(72,92,17,0.6)" },
    { h: 40, peak: 0.55, dur: "1.6s", del: "0.35s",  col: "rgba(72,92,17,0.4)" },
    { h: 75, peak: 1.12, dur: "2.0s", del: "0.05s",  col: "rgba(239,159,42,0.55)" },
    { h: 52, peak: 0.7,  dur: "1.8s", del: "0.45s",  col: "rgba(72,92,17,0.5)" },
  ];

  return (
    <div className="absolute inset-[14%] flex flex-col justify-between">
      {/* sparkline equity curve at top */}
      <svg viewBox="0 0 200 36" className="w-full opacity-70" preserveAspectRatio="none">
        <defs>
          <linearGradient id="eq-g" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(72,92,17,0.35)" />
            <stop offset="100%" stopColor="rgba(72,92,17,0)" />
          </linearGradient>
        </defs>
        <path d="M0 28 L25 24 L50 26 L75 18 L100 20 L125 11 L150 14 L175 6 L200 3"
          fill="none" stroke="#485c11" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M0 28 L25 24 L50 26 L75 18 L100 20 L125 11 L150 14 L175 6 L200 3 L200 36 L0 36Z"
          fill="url(#eq-g)" />
        {/* live pulse dot at the end */}
        <circle cx="200" cy="3" r="3" fill="#485c11">
          <animate attributeName="r" values="3;5;3" dur="1.4s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="1;0.4;1" dur="1.4s" repeatCount="indefinite" />
        </circle>
      </svg>

      {/* live bar chart */}
      <div className="flex items-end justify-between gap-[5%]" style={{ height: "54%" }}>
        {bars.map((b, i) => (
          <div
            key={i}
            className="bar-live flex-1 rounded-t-[3px]"
            style={{
              height: `${b.h}%`,
              backgroundColor: b.col,
              "--peak": b.peak,
              "--dur": b.dur,
              "--del": b.del,
            } as React.CSSProperties}
          />
        ))}
      </div>

      {/* status row */}
      <div className="flex items-center gap-[6%]">
        <span className="h-1.5 w-1.5 rounded-full bg-olive-bright" style={{ boxShadow: "0 0 4px 1px rgba(111,143,26,0.8)" }}>
          <style>{`@keyframes live-ping{0%,100%{opacity:1}50%{opacity:.3}}`}</style>
        </span>
        <span className="font-mono text-[7px] uppercase tracking-widest text-olive">Live · paper</span>
        <span className="ml-auto font-mono text-[8px] font-bold text-olive">+18.4%</span>
      </div>
    </div>
  );
}

/* OBSERVE — green dots travelling along circuit paths (event log / glass box) */
function ObserveDots() {
  // SVG paths for the dots to travel along
  const paths = [
    { d: "M20,60 L80,60 L80,120 L180,120", delay: "0s",   dur: "2.6s" },
    { d: "M40,30 L120,30 L120,90 L200,90", delay: "0.9s", dur: "3.1s" },
    { d: "M10,100 L60,100 L60,150 L160,150", delay: "1.7s", dur: "2.4s" },
    { d: "M30,70 L100,70 L100,40 L190,40", delay: "0.4s", dur: "2.9s" },
  ];

  return (
    <div className="absolute inset-[8%]">
      {/* static dot grid — the "matrix" */}
      <div
        className="absolute inset-0 rounded-[16px] opacity-50"
        style={{
          backgroundImage: "radial-gradient(rgba(72,92,17,0.6) 1.4px, transparent 1.6px)",
          backgroundSize: "16px 16px",
        }}
      />
      {/* animated travelling dots */}
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 220 180" overflow="visible">
        <defs>
          {paths.map((p, i) => (
            <path key={i} id={`obs-path-${i}`} d={p.d} fill="none" />
          ))}
        </defs>
        {/* faint trace lines */}
        {paths.map((p, i) => (
          <path key={i} d={p.d} fill="none" stroke="rgba(72,92,17,0.18)" strokeWidth="1.5" strokeDasharray="4 6" />
        ))}
        {/* travelling glowing dots */}
        {paths.map((p, i) => (
          <circle key={i} r="4" fill="#6f8f1a">
            <animateMotion
              dur={p.dur}
              repeatCount="indefinite"
              begin={p.delay}
              calcMode="spline"
              keyTimes="0;1"
              keySplines="0.45 0 0.55 1"
            >
              <mpath href={`#obs-path-${i}`} />
            </animateMotion>
            <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.08;0.92;1" dur={p.dur} repeatCount="indefinite" begin={p.delay} />
            <animate attributeName="r" values="3;5;3" dur="0.9s" repeatCount="indefinite" />
            {/* glow filter applied inline */}
            <filter id={`glow-${i}`}>
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </circle>
        ))}
        {/* larger glow circles behind the dots */}
        {paths.map((p, i) => (
          <circle key={`glow-${i}`} r="8" fill="rgba(111,143,26,0.3)">
            <animateMotion
              dur={p.dur}
              repeatCount="indefinite"
              begin={p.delay}
              calcMode="spline"
              keyTimes="0;1"
              keySplines="0.45 0 0.55 1"
            >
              <mpath href={`#obs-path-${i}`} />
            </animateMotion>
            <animate attributeName="opacity" values="0;0.6;0.6;0" keyTimes="0;0.08;0.92;1" dur={p.dur} repeatCount="indefinite" begin={p.delay} />
          </circle>
        ))}
      </svg>
    </div>
  );
}

/* Edge label with a leader line — visible only while its layer is active. */
function EdgeLabel({
  text,
  side,
  top,
  focus,
}: {
  text: string;
  side: "left" | "right";
  top: string;
  focus: MotionValue<number>;
}) {
  const opacity = useTransform(focus, [0, 0.6, 1], [0, 0.55, 1]);
  const lineScale = useTransform(focus, [0, 1], [0.6, 1.5]);

  return (
    <motion.div
      className="pointer-events-none absolute z-20 hidden items-center gap-2.5 text-olive lg:flex"
      style={{
        top,
        [side === "right" ? "right" : "left"]: "-2%",
        flexDirection: side === "right" ? "row" : "row-reverse",
        opacity,
      }}
    >
      <span className="eyebrow whitespace-nowrap font-semibold tracking-[0.16em]">
        {text}
      </span>
      <motion.span
        className="h-px w-9 bg-current"
        style={{
          scaleX: lineScale,
          transformOrigin: side === "right" ? "left" : "right",
        }}
      />
    </motion.div>
  );
}

/* The glowing centerpiece orb — Doomberg's mark, counter-rotated to face the
   camera so it "pops" cleanly above the top plane. */
function Orb() {
  return (
    <div
      className="absolute left-1/2 top-1/2"
      style={{ transform: "translate(-50%, -50%) translateZ(70px) rotateZ(45deg) rotateX(-54deg)" }}
    >
      <div className="relative grid place-items-center">
        <div className="animate-orb-glow absolute h-24 w-24 rounded-full bg-[radial-gradient(circle,rgba(218,161,57,0.6),transparent_66%)] blur-md" />
        <div className="relative grid h-[72px] w-[72px] place-items-center rounded-[24px] bg-gradient-to-br from-gold to-olive shadow-[0_16px_36px_-10px_rgba(91,75,36,0.85),inset_0_2px_6px_rgba(255,255,255,0.45)]">
          <span className="grid h-8 w-8 rotate-45 place-items-center rounded-[7px] bg-cream/95">
            <span className="h-3 w-3 rotate-45 rounded-[3px] bg-olive" />
          </span>
        </div>
      </div>
    </div>
  );
}
