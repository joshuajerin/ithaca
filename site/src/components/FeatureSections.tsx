import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { Eyebrow, Reveal } from "./ui";
import { rise, stagger, inView, popIn } from "../lib/motion";

type Feature = { icon: ReactNode; title: string; body: string };
type Block = {
  id: string;
  eyebrow: string;
  title: ReactNode;
  copy: string;
  side: "left" | "right"; // which side the illustrated card sits on
  illustration: "map" | "dots" | "matrix";
  features: Feature[];
};

const BLOCKS: Block[] = [
  {
    id: "tools",
    eyebrow: "Tools layer",
    title: (
      <>
        The agent's interface
        <br /> to the markets
      </>
    ),
    copy: "Your agent connects over MCP, discovers a catalog of vetted research tools, and calls them. Every result comes back typed, with a mandatory provenance block.",
    side: "right",
    illustration: "map",
    features: [
      { icon: <IconNodes />, title: "Discover tools over MCP", body: "OHLCV, fundamentals, signals, news, filings, order-book replay." },
      { icon: <IconDoc />, title: "Typed I/O with provenance", body: "Source, as-of, freshness, PIT, coverage, cost on every call." },
      { icon: <IconClock />, title: "Per-call deadlines & budgets", body: "Sessions carry an aggregate wall-clock cap — no runaway runs." },
    ],
  },
  {
    id: "execution",
    eyebrow: "Execution layer",
    title: (
      <>
        Strategies as data,
        <br /> not code we run
      </>
    ),
    copy: "The agent proposes a strategy as a declarative spec. We validate it against the operator registry, backtest it point-in-time, then paper-trade it on workers that import the very same core.",
    side: "left",
    illustration: "dots",
    features: [
      { icon: <IconLayers />, title: "Declarative StrategySpec", body: "A closed, validated schema — there is no free-form code field." },
      { icon: <IconChart />, title: "No-lookahead backtests", body: "Walk-forward, Monte Carlo, deflated Sharpe + PBO by default." },
      { icon: <IconShield />, title: "Single-writer paper book", body: "Workers propose deltas; the control plane applies them serially." },
    ],
  },
  {
    id: "observability",
    eyebrow: "Observability layer",
    title: (
      <>
        A glass box that
        <br /> records everything
      </>
    ),
    copy: "Because Doomberg is the server your agent calls, every tool call is an observation point. Watch the reasoning, the tool timeline, and the evidence panels live — or scrub the whole run back.",
    side: "right",
    illustration: "matrix",
    features: [
      { icon: <IconNodes />, title: "Live trace + replay", body: "Reasoning → tool calls → evidence panels, event-sourced." },
      { icon: <IconChart />, title: "Evidence panels", body: "~80 quant renderers map tool outputs to a question's answer." },
      { icon: <IconShield />, title: "Full audit log", body: "The event log is the audit trail — every call attributable." },
    ],
  },
];

export default function FeatureSections() {
  return (
    <section id="features" className="relative bg-paper">
      <div className="pointer-events-none absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-gradient-to-b from-transparent via-line to-transparent" />
      <div className="relative mx-auto max-w-[1200px] space-y-24 px-5 py-24 lg:space-y-36 lg:py-32">
        {BLOCKS.map((b) => (
          <FeatureBlock key={b.id} block={b} />
        ))}
      </div>
    </section>
  );
}

function FeatureBlock({ block }: { block: Block }) {
  const textCol = (
    <div className={block.side === "right" ? "lg:pr-8" : "lg:order-2 lg:pl-8"}>
      <Reveal>
        <Eyebrow tone={block.id === "execution" ? "muted" : "olive"}>
          {block.eyebrow}
        </Eyebrow>
      </Reveal>
      <Reveal delay={0.05}>
        <h2 className="display mt-5 text-[2.2rem] leading-[1.05] text-ink sm:text-[2.7rem] lg:text-[3rem]">
          {block.title}
        </h2>
      </Reveal>
      <Reveal delay={0.1}>
        <p className="mt-5 max-w-[46ch] text-[1.05rem] leading-relaxed text-muted">
          {block.copy}
        </p>
      </Reveal>

      <motion.ul
        variants={stagger(0.12, 0.15)}
        initial="hidden"
        whileInView="show"
        viewport={inView}
        className="mt-8 space-y-3.5"
      >
        {block.features.map((f) => (
          <motion.li key={f.title} variants={rise} className="flex gap-4">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-line-strong bg-cream text-olive">
              {f.icon}
            </span>
            <div>
              <h3 className="text-[1.02rem] font-500 text-ink">{f.title}</h3>
              <p className="mt-0.5 text-[0.92rem] leading-relaxed text-muted">
                {f.body}
              </p>
            </div>
          </motion.li>
        ))}
      </motion.ul>
    </div>
  );

  const cardCol = (
    <motion.div
      variants={popIn}
      initial="hidden"
      whileInView="show"
      viewport={inView}
      className={block.side === "right" ? "" : "lg:order-1"}
    >
      <IllustratedCard block={block} />
    </motion.div>
  );

  return (
    <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-2 lg:gap-16">
      {textCol}
      {cardCol}
    </div>
  );
}

/* The big rounded card with a layered background illustration + floating
   feature chips that drift in. */
function IllustratedCard({ block }: { block: Block }) {
  return (
    <div className="relative aspect-[4/3.1] w-full overflow-hidden rounded-[26px] border border-line-strong bg-gradient-to-br from-sand-2 to-cream-2 shadow-[0_50px_120px_-60px_rgba(24,23,15,0.5)]">
      <CardBackground kind={block.illustration} />

      {/* floating chips echoing each feature, drifting in sequentially */}
      <motion.div
        variants={stagger(0.16, 0.25)}
        initial="hidden"
        whileInView="show"
        viewport={inView}
        className="absolute inset-0 p-6"
      >
        {block.features.map((f, i) => (
          <motion.div
            key={f.title}
            variants={rise}
            className="absolute flex items-center gap-2.5 rounded-xl border border-line-strong bg-paper/90 px-3.5 py-2.5 shadow-[0_14px_30px_-18px_rgba(24,23,15,0.5)] backdrop-blur-sm"
            style={chipPos(i)}
          >
            <span className="text-olive">{f.icon}</span>
            <span className="text-[0.84rem] font-500 text-ink">{f.title}</span>
          </motion.div>
        ))}
      </motion.div>
    </div>
  );
}

function chipPos(i: number): React.CSSProperties {
  return [
    { left: "8%", top: "16%" },
    { right: "10%", top: "44%" },
    { left: "14%", bottom: "14%" },
  ][i];
}

function CardBackground({ kind }: { kind: Block["illustration"] }) {
  if (kind === "matrix") {
    return (
      <>
        <div className="animate-matrix absolute inset-0 opacity-50 [background-image:radial-gradient(rgba(72,92,17,0.4)_1px,transparent_1.4px)] [background-size:13px_13px]" />
        <div className="absolute inset-0 bg-gradient-to-t from-cream-2/80 to-transparent" />
      </>
    );
  }
  if (kind === "dots") {
    return (
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            "radial-gradient(rgba(91,75,36,0.22) 1.4px, transparent 1.4px)",
          backgroundSize: "20px 20px",
        }}
      />
    );
  }
  // map grid + scattered "blocks"
  return (
    <>
      <div
        className="absolute inset-0 opacity-70"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(91,75,36,0.13) 1px, transparent 1px), linear-gradient(to bottom, rgba(91,75,36,0.13) 1px, transparent 1px)",
          backgroundSize: "46px 46px",
        }}
      />
      {[
        { l: "20%", t: "22%", w: "18%", h: "20%" },
        { l: "60%", t: "30%", w: "20%", h: "24%" },
        { l: "30%", t: "58%", w: "26%", h: "18%" },
      ].map((s, i) => (
        <span
          key={i}
          className="absolute rounded-lg border border-line-strong bg-paper/40"
          style={{ left: s.l, top: s.t, width: s.w, height: s.h }}
        />
      ))}
    </>
  );
}

/* ---- tiny line icons (inline SVG, 18px) --------------------------------- */
const sw = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
function IconNodes() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...sw}>
      <circle cx="6" cy="6" r="2.2" /><circle cx="18" cy="6" r="2.2" /><circle cx="12" cy="18" r="2.2" />
      <path d="M7.7 7.5 10.6 16M16.3 7.5 13.4 16M8 6h8" />
    </svg>
  );
}
function IconDoc() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...sw}>
      <path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 12h6M9 16h6" />
    </svg>
  );
}
function IconClock() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...sw}>
      <circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" />
    </svg>
  );
}
function IconLayers() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...sw}>
      <path d="M12 3 21 8l-9 5-9-5z" /><path d="M3 13l9 5 9-5" />
    </svg>
  );
}
function IconChart() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...sw}>
      <path d="M4 19V5M4 19h16" /><path d="M8 15l3-4 3 2 4-6" />
    </svg>
  );
}
function IconShield() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...sw}>
      <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" /><path d="M9 12l2 2 4-4" />
    </svg>
  );
}
