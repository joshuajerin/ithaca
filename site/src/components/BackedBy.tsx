import { motion } from "framer-motion";
import { Reveal } from "./ui";
import { rise, stagger, inView } from "../lib/motion";

// Tier 1 — primary data + infra the platform is built on.
const PRIMARY = ["Databento", "Sharadar", "Alpaca", "DigitalOcean", "PostgreSQL"];

// Tier 2 — the wider source ecosystem.
const ECOSYSTEM = [
  "SEC EDGAR",
  "FRED / ALFRED",
  "IEX DEEP",
  "Nasdaq ITCH",
  "NYSE Pillar",
  "Cboe PITCH",
  "OPRA",
  "Model Context Protocol",
  "Anthropic Claude",
  "OpenAI",
];

function Wordmark({ name }: { name: string }) {
  // A simple, consistent wordmark: small mark + name, rendered in muted tan.
  return (
    <span className="flex items-center gap-2.5">
      <span className="grid h-5 w-5 place-items-center">
        <span className="h-3.5 w-3.5 rotate-45 rounded-[3px] border-2 border-current" />
      </span>
      <span className="text-[1.02rem] font-600 tracking-tight">{name}</span>
    </span>
  );
}

export default function BackedBy() {
  return (
    <section id="built" className="relative bg-paper py-24 lg:py-28">
      <div className="mx-auto max-w-[1200px] px-5">
        <Reveal className="text-center">
          <p className="eyebrow text-faint">Built on professional-grade data</p>
        </Reveal>

        {/* primary tier — tan rounded cards */}
        <motion.div
          variants={stagger(0.08)}
          initial="hidden"
          whileInView="show"
          viewport={inView}
          className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
        >
          {PRIMARY.map((p) => (
            <motion.div
              key={p}
              variants={rise}
              className="grid h-24 place-items-center rounded-2xl bg-sand/70 text-gold-deep transition-colors duration-300 hover:bg-sand"
            >
              <Wordmark name={p} />
            </motion.div>
          ))}
        </motion.div>

        {/* ecosystem tier — muted inline wordmarks */}
        <Reveal className="mt-16 text-center">
          <p className="eyebrow text-faint">Source ecosystem</p>
        </Reveal>
        <motion.div
          variants={stagger(0.05)}
          initial="hidden"
          whileInView="show"
          viewport={inView}
          className="mt-8 flex flex-wrap items-center justify-center gap-x-10 gap-y-6"
        >
          {ECOSYSTEM.map((e) => (
            <motion.span
              key={e}
              variants={rise}
              className="text-tan transition-colors duration-300 hover:text-gold-deep"
            >
              <Wordmark name={e} />
            </motion.span>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
