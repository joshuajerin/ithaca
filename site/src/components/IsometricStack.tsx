import { motion } from "framer-motion";
import { EASE } from "../lib/motion";

/* --------------------------------------------------------------------------
 * The signature visual: three floating isometric slabs that represent the
 * platform's three layers. Built with pure CSS 3D transforms — no WebGL.
 *
 *   Tools layer        (top)    — the agent's interface: callable MCP tools
 *   Execution layer    (middle) — declarative specs run on trusted infra
 *   Observability layer(bottom) — the event log / glass box, a data matrix
 * ------------------------------------------------------------------------ */

const LABELS = [
  { text: "Tools layer", side: "right", top: "20%", tone: "text-olive" },
  { text: "Execution layer", side: "left", top: "47%", tone: "text-tan" },
  { text: "Observability layer", side: "right", top: "74%", tone: "text-olive-bright" },
];

export default function IsometricStack() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-15%" }}
      transition={{ duration: 1, ease: EASE }}
      className="relative mx-auto w-full max-w-[760px]"
    >
      {/* edge labels with dotted leader lines */}
      {LABELS.map((l) => (
        <div
          key={l.text}
          className="pointer-events-none absolute z-20 hidden items-center gap-2 md:flex"
          style={{
            top: l.top,
            [l.side === "right" ? "right" : "left"]: "-2%",
            flexDirection: l.side === "right" ? "row" : "row-reverse",
          }}
        >
          <span className={`eyebrow ${l.tone}`}>{l.text}</span>
          <span
            className="h-px w-10 bg-current opacity-30"
            style={{ color: "currentColor" }}
          />
        </div>
      ))}

      {/* the 3D scene */}
      <div
        className="relative mx-auto"
        style={{ perspective: "1500px", perspectiveOrigin: "50% 38%" }}
      >
        <div
          className="preserve-3d relative mx-auto aspect-[1.35/1] w-full max-w-[620px]"
          style={{ transform: "rotateX(56deg) rotateZ(-45deg)" }}
        >
          {/* BOTTOM — observability / data matrix */}
          <Plane className="bob-bot">
            <div className="absolute inset-0 rounded-[26px] border-2 border-olive/35 bg-paper" />
            <div className="animate-matrix absolute inset-[6px] rounded-[20px] opacity-70 [background-image:radial-gradient(rgba(72,92,17,0.45)_1px,transparent_1.4px)] [background-size:14px_14px]" />
            <Tiles tone="olive" />
          </Plane>

          {/* MIDDLE — execution / trusted infra */}
          <Plane className="bob-mid">
            <div className="absolute inset-0 rounded-[26px] border border-line-strong bg-gradient-to-br from-sand-2 to-cream-2 shadow-[0_30px_60px_-30px_rgba(24,23,15,0.4)]" />
            <Grid />
            <Tiles tone="sand" />
          </Plane>

          {/* TOP — tools / agent interface, carries the glowing orb */}
          <Plane className="bob-top">
            <div className="absolute inset-0 rounded-[26px] border border-gold/40 bg-gradient-to-br from-sand to-[#f6e8cf] shadow-[0_40px_80px_-30px_rgba(91,75,36,0.5)]" />
            <Grid strong />
            <Tiles tone="gold" />
            <Orb />
          </Plane>
        </div>
      </div>
    </motion.div>
  );
}

function Plane({
  children,
  className,
}: {
  children: React.ReactNode;
  className: string;
}) {
  return (
    <div className={`preserve-3d absolute inset-0 ${className}`}>{children}</div>
  );
}

/* Faint "city map" street grid drawn with layered gradients. */
function Grid({ strong = false }: { strong?: boolean }) {
  const o = strong ? 0.18 : 0.1;
  return (
    <div
      className="absolute inset-[6px] rounded-[20px]"
      style={{
        backgroundImage: `linear-gradient(to right, rgba(91,75,36,${o}) 1px, transparent 1px), linear-gradient(to bottom, rgba(91,75,36,${o}) 1px, transparent 1px)`,
        backgroundSize: "44px 44px",
      }}
    />
  );
}

/* Scattered rounded "tiles" — the tool/service nodes sitting on each plane. */
function Tiles({ tone }: { tone: "gold" | "sand" | "olive" }) {
  const fill =
    tone === "gold"
      ? "bg-white/70 border-gold/30"
      : tone === "sand"
        ? "bg-white/60 border-line-strong"
        : "bg-white/80 border-olive/25";
  const spots = [
    { l: "12%", t: "20%", w: "26%", h: "16%" },
    { l: "62%", t: "16%", w: "24%", h: "14%" },
    { l: "16%", t: "58%", w: "22%", h: "18%" },
    { l: "58%", t: "60%", w: "28%", h: "15%" },
    { l: "40%", t: "40%", w: "20%", h: "13%" },
  ];
  return (
    <>
      {spots.map((s, i) => (
        <span
          key={i}
          className={`absolute rounded-lg border ${fill}`}
          style={{ left: s.l, top: s.t, width: s.w, height: s.h }}
        />
      ))}
    </>
  );
}

/* The glowing centerpiece orb — Doomberg's mark, counter-rotated to face the
   camera so it "pops" above the top plane. */
function Orb() {
  return (
    <div
      className="absolute left-1/2 top-1/2"
      style={{ transform: "translate(-50%, -50%) translateZ(64px) rotateZ(45deg) rotateX(-56deg)" }}
    >
      <div className="relative grid place-items-center">
        <div className="animate-orb-glow absolute h-28 w-28 rounded-full bg-[radial-gradient(circle,rgba(218,161,57,0.65),transparent_65%)] blur-md" />
        <div className="relative grid h-20 w-20 place-items-center rounded-[28px] bg-gradient-to-br from-gold to-olive shadow-[0_18px_40px_-12px_rgba(91,75,36,0.8),inset_0_2px_6px_rgba(255,255,255,0.4)]">
          <span className="grid h-9 w-9 rotate-45 place-items-center rounded-[8px] bg-cream/90">
            <span className="h-3.5 w-3.5 rotate-45 rounded-[3px] bg-olive" />
          </span>
        </div>
      </div>
    </div>
  );
}
