import { motion } from "framer-motion";
import { Eyebrow, Reveal } from "./ui";
import { rise, stagger, inView, popIn } from "../lib/motion";

const THOUGHTS = [
  "Check whether NVDA's datacenter momentum is still intact, then size it.",
  "Margins hold and news is constructive — momentum signal looks tradable.",
  "Backtest cleared walk-forward. Propose a paper deployment for review.",
];

const CALLS: [string, string, "ok" | "slow" | "run"][] = [
  ["fundamentals.get  NVDA", "120ms", "ok"],
  ['news.search  "datacenter"', "240ms", "ok"],
  ["signals.evaluate  momentum", "90ms", "ok"],
  ["insider.activity  NVDA", "1.4s", "slow"],
  ["backtest.run  momentum/NVDA", "2.3s", "run"],
];

export default function GlassBox() {
  return (
    <section id="glassbox" className="relative overflow-hidden bg-cream/40 py-24 lg:py-32">
      <div className="bg-dotgrid mask-fade-y pointer-events-none absolute inset-0 opacity-50" />
      <div className="relative mx-auto max-w-[1200px] px-5">
        <div className="grid grid-cols-1 items-end gap-6 lg:grid-cols-[1fr_minmax(0,30rem)]">
          <div>
            <Reveal>
              <Eyebrow>The glass box</Eyebrow>
            </Reveal>
            <Reveal delay={0.05}>
              <h2 className="display mt-5 max-w-[16ch] text-[2.4rem] leading-[1.03] text-ink sm:text-5xl lg:text-[3.4rem]">
                Watch your agent think, work, and trade
              </h2>
            </Reveal>
          </div>
          <Reveal delay={0.1}>
            <p className="text-[1.05rem] leading-relaxed text-muted lg:text-right">
              No chat console. The conversation <em>is</em> the trace — reasoning
              on the left, every tool call in the middle, the panel each call
              produced on the right. Live, or scrubbed back to any moment.
            </p>
          </Reveal>
        </div>

        {/* The big three-column trace */}
        <motion.div
          variants={popIn}
          initial="hidden"
          whileInView="show"
          viewport={inView}
          className="relative mt-12 overflow-hidden rounded-[22px] border border-line-strong bg-paper shadow-[0_50px_140px_-60px_rgba(24,23,15,0.55)]"
        >
          {/* header */}
          <div className="flex flex-wrap items-center gap-3 border-b border-line bg-cream/60 px-5 py-3.5">
            <span className="flex items-center gap-2 font-mono text-[0.74rem] text-ink">
              <span className="h-2 w-2 animate-pulse-dot rounded-full bg-olive" />
              run · research-NVDA-0617
            </span>
            <span className="hidden font-mono text-[0.72rem] text-faint sm:inline">
              agent: claude
            </span>
            {/* aggregate deadline bar — a UI-first answer to "no aggregate deadline" */}
            <div className="ml-auto flex items-center gap-2">
              <span className="font-mono text-[0.68rem] uppercase tracking-wider text-faint">
                run deadline
              </span>
              <span className="h-1.5 w-28 overflow-hidden rounded-full bg-line">
                <span className="block h-full w-[42%] rounded-full bg-olive" />
              </span>
              <span className="font-mono text-[0.68rem] text-faint">00:42 / 02:00</span>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-px bg-line lg:grid-cols-[0.95fr_1fr_1.15fr]">
            {/* Reasoning rail */}
            <div className="bg-paper p-5">
              <p className="eyebrow text-faint">reasoning</p>
              <motion.div
                variants={stagger(0.18, 0.2)}
                initial="hidden"
                whileInView="show"
                viewport={inView}
                className="mt-4 space-y-3"
              >
                {THOUGHTS.map((t, i) => (
                  <motion.p
                    key={i}
                    variants={rise}
                    className={`rounded-xl px-3.5 py-2.5 text-[0.84rem] leading-relaxed ${
                      i === 0 ? "bg-leaf text-olive-700" : "bg-cream text-ink-soft"
                    }`}
                  >
                    {t}
                  </motion.p>
                ))}
              </motion.div>
            </div>

            {/* Tool timeline */}
            <div className="bg-paper p-5">
              <p className="eyebrow text-faint">tool calls</p>
              <motion.ul
                variants={stagger(0.12, 0.3)}
                initial="hidden"
                whileInView="show"
                viewport={inView}
                className="mt-4 space-y-2.5 font-mono text-[0.76rem]"
              >
                {CALLS.map(([name, ms, st]) => (
                  <motion.li
                    key={name}
                    variants={rise}
                    className="flex items-center justify-between rounded-xl border border-line px-3 py-2"
                  >
                    <span className="flex items-center gap-2.5 text-ink">
                      <StatusDot st={st} /> {name}
                    </span>
                    <span className={st === "slow" ? "text-gold" : "text-faint"}>
                      {st === "slow" ? "⚠ " : ""}
                      {ms}
                    </span>
                  </motion.li>
                ))}
              </motion.ul>
            </div>

            {/* Evidence panels */}
            <div className="bg-paper p-5">
              <p className="eyebrow text-faint">evidence</p>
              <motion.div
                variants={stagger(0.16, 0.5)}
                initial="hidden"
                whileInView="show"
                viewport={inView}
                className="mt-4 space-y-3"
              >
                <motion.div variants={popIn} className="rounded-xl border border-line bg-cream/50 p-3.5">
                  <div className="flex items-center justify-between text-[0.8rem]">
                    <span className="font-medium text-ink">FundamentalsPanel</span>
                    <span className="font-mono text-olive">rev +22% · GM 73%</span>
                  </div>
                  <div className="mt-3 grid grid-cols-4 gap-1.5">
                    {[60, 78, 52, 88].map((h, i) => (
                      <span key={i} className="flex h-12 items-end">
                        <span
                          className="w-full rounded-sm bg-olive/70"
                          style={{ height: `${h}%` }}
                        />
                      </span>
                    ))}
                  </div>
                </motion.div>
                <motion.div variants={popIn} className="rounded-xl border border-line bg-cream/50 p-3.5">
                  <div className="flex items-center justify-between text-[0.8rem]">
                    <span className="font-medium text-ink">BacktestPanel</span>
                    <span className="font-mono text-olive">Sharpe 1.84</span>
                  </div>
                  <EquityCurve />
                  <div className="mt-1.5 flex items-center justify-between font-mono text-[0.66rem] text-faint">
                    <span>walk-forward · PIT</span>
                    <span className="text-gold-deep">deflated ✓ · PBO 0.18</span>
                  </div>
                </motion.div>
              </motion.div>
            </div>
          </div>

          {/* scrubber */}
          <div className="flex items-center gap-3 border-t border-line bg-cream/40 px-5 py-3">
            <button className="grid h-7 w-7 place-items-center rounded-full bg-olive text-cream" aria-label="play">
              ▶
            </button>
            <span className="relative h-1.5 flex-1 rounded-full bg-line">
              <span className="absolute inset-y-0 left-0 w-[42%] rounded-full bg-olive/60" />
              <span className="absolute left-[42%] top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-paper bg-olive shadow" />
            </span>
            <span className="font-mono text-[0.7rem] text-faint">00:42 / live</span>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function StatusDot({ st }: { st: "ok" | "slow" | "run" }) {
  const cls =
    st === "ok"
      ? "bg-olive"
      : st === "slow"
        ? "bg-gold"
        : "bg-olive-bright animate-pulse-dot";
  return <span className={`h-2 w-2 shrink-0 rounded-full ${cls}`} />;
}

function EquityCurve() {
  return (
    <svg viewBox="0 0 260 60" className="mt-2 h-16 w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="eq2" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(72,92,17,0.26)" />
          <stop offset="100%" stopColor="rgba(72,92,17,0)" />
        </linearGradient>
      </defs>
      <motion.path
        d="M0 50 L30 46 L60 49 L90 36 L120 40 L150 26 L180 30 L210 15 L260 6"
        fill="none"
        stroke="#485c11"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 1.4, ease: "easeOut", delay: 0.6 }}
      />
      <path
        d="M0 50 L30 46 L60 49 L90 36 L120 40 L150 26 L180 30 L210 15 L260 6 L260 60 L0 60 Z"
        fill="url(#eq2)"
      />
    </svg>
  );
}
