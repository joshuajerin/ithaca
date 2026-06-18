import { useRef } from "react";
import {
  motion,
  useScroll,
  useTransform,
  useSpring,
  useReducedMotion,
  useMotionValue,
} from "framer-motion";
import type { MotionValue } from "framer-motion";
import { Eyebrow } from "./ui";
import { rise, inView, EASE } from "../lib/motion";
import IsometricStack from "./IsometricStack";

/* --------------------------------------------------------------------------
 * "Three layers. One platform." — a pinned, scroll-driven scrollytelling
 * section.
 *
 *   • Left column: text that cross-fades per step.
 *   • Right column: the isometric 3-slab stack, pinned to the viewport.
 *
 * On enter, the whole stack is sharp and equally weighted. As the user scrolls
 * through three focus steps, ONE layer becomes the focus (sharp, lifted, label
 * emphasized) while the others blur + dim — a depth-of-field rack focus. The
 * left text swaps to the active layer's title + copy, synced to scroll.
 *
 * The third layer ("Observe") is a PLACEHOLDER name — rename it in LAYERS.
 * ------------------------------------------------------------------------ */

type Layer = {
  key: "data" | "deploy" | "observe";
  edge: string;
  title: string;
  body: string;
};

const LAYERS: Layer[] = [
  {
    key: "data",
    edge: "Data layer",
    title: "Data",
    body: "Vetted, professional-grade market data — point-in-time, survivorship-bias-free, with provenance on every result. The sources your agent reasons over.",
  },
  {
    key: "deploy",
    edge: "Deploy layer",
    title: "Deploy",
    body: "Declarative strategy specs validated as data, backtested and paper-traded on trusted infrastructure. A single writer owns the money path.",
  },
  {
    key: "observe",
    edge: "Observe layer",
    title: "Observe",
    body: "Every tool call, fill, and decision recorded to a replayable, audited event log — the glass box your agent's whole run plays back from.",
  },
];

const INTRO =
  "Your agent runs the workflow. Doomberg runs the tools, the execution, and the recording — research, deployment, and oversight in one trusted place.";

export default function HowItWorks() {
  const reduceMotion = useReducedMotion();

  return (
    <section id="how" className="relative bg-paper">
      {/* Desktop: pinned scrollytelling. Hidden when reduced-motion is on. */}
      {!reduceMotion && (
        <div className="hidden lg:block">
          <Scrollytelling />
        </div>
      )}

      {/* Mobile + reduced-motion: graceful static fallback (visual on top,
          then the three layers explained as plain step cards). */}
      <div className={reduceMotion ? "block" : "block lg:hidden"}>
        <StaticFallback />
      </div>
    </section>
  );
}

/* ========================================================================== */
/* Pinned, scroll-driven experience (lg+, motion allowed).                    */
/* ========================================================================== */

function Scrollytelling() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end end"],
  });

  // Smooth the raw scroll progress so focus transitions feel like a rack focus.
  const p = useSpring(scrollYProgress, {
    stiffness: 120,
    damping: 28,
    restDelta: 0.001,
  });

  // ---- Stack separation (0 = stacked tight/together, 1 = spread apart) -----
  // Together at the start, then separate "a decent amount" past the initial
  // point and hold the full separated stack before isolating layers.
  const separation = useTransform(p, [0, 0.05, 0.18, 1], [0, 0, 1, 1]);

  // ---- Per-layer visibility (1 = shown, 0 = REMOVED entirely) --------------
  // Timeline (progress 0→1):
  //   0.00–0.18  together → separate   — all three layers shown.
  //   0.18–0.24  dwell                 — full separated stack, all shown.
  //   0.28–0.45  DATA only (top)       — the other two removed.
  //   0.49–0.66  DEPLOY only (mid).
  //   0.74–1.00  OBSERVE only (bottom).
  // Each layer hands off to the next; exactly one is shown during a step.
  const focusTop = useTransform(p, [0, 0.45, 0.49, 1], [1, 1, 0, 0]);
  const focusMid = useTransform(
    p,
    [0, 0.24, 0.28, 0.45, 0.49, 0.66, 0.7, 1],
    [1, 1, 0, 0, 1, 1, 0, 0],
  );
  const focusBot = useTransform(
    p,
    [0, 0.24, 0.28, 0.7, 0.74, 1],
    [1, 1, 0, 0, 1, 1],
  );

  return (
    // Tall scroll track — its height is what we scroll through. The inner panel
    // pins (sticky) while we traverse it.
    <div ref={ref} className="relative h-[340vh]">
      <div className="sticky top-0 flex h-screen items-center overflow-hidden">
        {/* center guide line, echoing the hero */}
        <div className="pointer-events-none absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-gradient-to-b from-transparent via-line to-transparent" />

        <div className="relative mx-auto grid w-full max-w-[1200px] grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] items-center gap-16 px-6 xl:gap-24">
          {/* LEFT — text that swaps per step */}
          <div className="relative">
            <motion.div
              initial="hidden"
              whileInView="show"
              viewport={inView}
              variants={rise}
            >
              <Eyebrow>How it works</Eyebrow>
            </motion.div>

            {/* The headline stays put; the step copy below it cross-fades. */}
            <h2 className="display mt-5 text-[2.4rem] leading-[1.03] text-ink xl:text-[3.2rem]">
              Three layers.
              <br />
              One platform.
            </h2>

            {/* Stacked text blocks — only one is visible at a time. Sized to a
                fixed min-height so the headline above never jumps. */}
            <div className="relative mt-7 min-h-[200px]">
              <StepText
                progress={p}
                band={[-0.05, 0, 0.22, 0.26]}
                eyebrowTone="muted"
                kicker="The platform"
                body={INTRO}
              />
              <StepText
                progress={p}
                band={[0.26, 0.3, 0.43, 0.47]}
                kicker="01 — Data layer"
                title={LAYERS[0].title}
                body={LAYERS[0].body}
              />
              <StepText
                progress={p}
                band={[0.47, 0.51, 0.64, 0.68]}
                kicker="02 — Deploy layer"
                title={LAYERS[1].title}
                body={LAYERS[1].body}
              />
              <StepText
                progress={p}
                band={[0.68, 0.72, 1, 1.05]}
                kicker="03 — Observe layer"
                title={LAYERS[2].title}
                body={LAYERS[2].body}
              />
            </div>

            {/* progress rail — three dots that light as you advance */}
            <div className="mt-10 flex items-center gap-3">
              {[
                [0.26, 0.47],
                [0.47, 0.68],
                [0.68, 1.01],
              ].map(([a, b], i) => (
                <ProgressDot key={i} progress={p} a={a} b={b} />
              ))}
            </div>
          </div>

          {/* RIGHT — the pinned isometric stack */}
          <div className="relative">
            <IsometricStack
              focus={{ top: focusTop, mid: focusMid, bot: focusBot }}
              separation={separation}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/* A single cross-fading text block. Visible (opacity 1, y 0) while scroll
   progress sits inside `range = [enterEnd, peak, exitStart]`. */
function StepText({
  progress,
  band,
  kicker,
  title,
  body,
  eyebrowTone = "olive",
}: {
  progress: MotionValue<number>;
  // [fadeInStart, fadeInEnd, fadeOutStart, fadeOutEnd] — non-overlapping across
  // steps so only one block is ever visible (no stacked/garbled text).
  band: [number, number, number, number];
  kicker: string;
  title?: string;
  body: string;
  eyebrowTone?: "olive" | "muted";
}) {
  const opacity = useTransform(progress, band, [0, 1, 1, 0]);
  const y = useTransform(progress, band, [16, 0, 0, -16]);

  return (
    <motion.div
      className="absolute inset-0"
      style={{ opacity, y }}
      aria-hidden="true"
    >
      <span
        className={`eyebrow ${eyebrowTone === "olive" ? "text-olive" : "text-faint"}`}
      >
        {kicker}
      </span>
      {title && (
        <h3 className="mt-3 text-[1.7rem] font-semibold leading-tight text-ink">
          {title}
        </h3>
      )}
      <p className="mt-3 max-w-[34rem] text-[1.05rem] leading-relaxed text-muted">
        {body}
      </p>
    </motion.div>
  );
}

/* A progress dot for the step rail — fills olive while its range is active. */
function ProgressDot({
  progress,
  a,
  b,
}: {
  progress: MotionValue<number>;
  a: number;
  b: number;
}) {
  const opacity = useTransform(progress, [a - 0.05, a, b, b + 0.001], [0.25, 1, 1, 0.25]);
  const scaleX = useTransform(progress, [a, b], [0.4, 1]);
  return (
    <div className="h-1.5 w-10 overflow-hidden rounded-full bg-line">
      <motion.div
        className="h-full w-full origin-left rounded-full bg-olive"
        style={{ opacity, scaleX }}
      />
    </div>
  );
}

/* ========================================================================== */
/* Static fallback — mobile + prefers-reduced-motion.                         */
/* No scroll-jacking: the full stack (all layers sharp) sits on top, then the */
/* three layers are explained in sequence as plain cards.                     */
/* ========================================================================== */

function StaticFallback() {
  // Constant "all in focus" + fully-separated values so the stack renders as
  // the full, spread-apart three-slab visual (no scroll-driven changes).
  const full = useFullFocus();
  const fullSep = useMotionValue(1);

  return (
    <div className="mx-auto max-w-[1100px] px-5 py-20 lg:py-28">
      <motion.div
        initial="hidden"
        whileInView="show"
        viewport={inView}
        variants={rise}
      >
        <Eyebrow>How it works</Eyebrow>
      </motion.div>
      <motion.h2
        variants={rise}
        initial="hidden"
        whileInView="show"
        viewport={inView}
        className="display mt-5 text-[2.4rem] leading-[1.03] text-ink sm:text-5xl"
      >
        Three layers.
        <br />
        One platform.
      </motion.h2>
      <motion.p
        variants={rise}
        initial="hidden"
        whileInView="show"
        viewport={inView}
        className="mt-5 max-w-[42rem] text-[1.05rem] leading-relaxed text-muted"
      >
        {INTRO}
      </motion.p>

      <div className="mt-24 overflow-visible">
        <IsometricStack focus={full} separation={fullSep} idle />
      </div>

      <div className="mx-auto mt-16 grid max-w-[920px] grid-cols-1 gap-px overflow-hidden rounded-2xl border border-line bg-line">
        {LAYERS.map((l, i) => (
          <motion.div
            key={l.key}
            variants={rise}
            initial="hidden"
            whileInView="show"
            viewport={inView}
            transition={{ delay: i * 0.06, ease: EASE }}
            className="bg-paper p-6"
          >
            <span className="eyebrow text-olive">
              {String(i + 1).padStart(2, "0")} — {l.edge}
            </span>
            <h3 className="mt-2 text-lg font-semibold text-ink">{l.title}</h3>
            <p className="mt-2 text-[0.92rem] leading-relaxed text-muted">
              {l.body}
            </p>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* Returns a focus set pinned at 1 for all layers (everything sharp). */
function useFullFocus() {
  const top = useMotionValue(1);
  const mid = useMotionValue(1);
  const bot = useMotionValue(1);
  return { top, mid, bot };
}
