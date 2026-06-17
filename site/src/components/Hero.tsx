import { motion } from "framer-motion";
import { EASE } from "../lib/motion";
import { Badge, PillButton } from "./ui";

/* Layered, slowly-drifting background: cream wash + soft color orbs + a faint
   grid and a center guide line. This is the depth the hero sits on. */
function HeroBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-b from-cream via-cream-2 to-paper" />
      <div className="animate-drift absolute -left-24 top-10 h-[34rem] w-[34rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(111,143,26,0.16),transparent_62%)] blur-2xl" />
      <div className="animate-drift-slow absolute -right-32 top-24 h-[38rem] w-[38rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(218,161,57,0.16),transparent_60%)] blur-2xl" />
      <div className="animate-drift absolute left-1/2 top-1/4 h-[26rem] w-[26rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_center,rgba(232,239,215,0.55),transparent_65%)] blur-3xl" />
      <div className="bg-grid mask-fade-y absolute inset-0 opacity-50" />
      <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-gradient-to-b from-transparent via-line-strong/60 to-transparent" />
    </div>
  );
}

export default function Hero() {
  const container = {
    hidden: {},
    show: { transition: { staggerChildren: 0.09, delayChildren: 0.15 } },
  };
  const item = {
    hidden: { opacity: 0, y: 22 },
    show: { opacity: 1, y: 0, transition: { duration: 0.8, ease: EASE } },
  };

  return (
    <section
      id="top"
      className="relative isolate overflow-hidden pb-28 pt-40 sm:pt-48 lg:pb-36 lg:pt-52"
    >
      <HeroBackdrop />

      <div className="relative mx-auto max-w-[1100px] px-5 text-center">
        <motion.div variants={container} initial="hidden" animate="show">
          <motion.div variants={item} className="flex justify-center">
            <Badge>Real exchange-grade data is live</Badge>
          </motion.div>

          <motion.h1
            variants={item}
            className="display mx-auto mt-7 max-w-[20ch] text-[3rem] leading-[1.0] text-ink sm:text-6xl lg:text-[5.6rem] lg:leading-[0.96]"
          >
            The tool-platform for
            <br className="hidden sm:block" /> the agent economy
          </motion.h1>

          <motion.p
            variants={item}
            className="mx-auto mt-7 max-w-[46ch] text-[1.12rem] leading-relaxed text-muted sm:text-[1.22rem]"
          >
            Doomberg gives autonomous agents vetted market tools, honest
            backtesting, and paper-trading on trusted infrastructure — recorded
            in a replayable glass box.
          </motion.p>

          <motion.div
            variants={item}
            className="mt-9 flex flex-wrap items-center justify-center gap-3"
          >
            <PillButton href="#cta" variant="primary" size="lg">
              Connect over MCP
            </PillButton>
            <PillButton href="#how" variant="secondary" size="lg">
              See how it works
            </PillButton>
          </motion.div>

          <motion.p
            variants={item}
            className="mt-7 font-mono text-[0.72rem] uppercase tracking-[0.16em] text-faint"
          >
            Never runs your agent · Never executes agent-authored code
          </motion.p>
        </motion.div>
      </div>
    </section>
  );
}
