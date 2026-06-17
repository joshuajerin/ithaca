import { motion } from "framer-motion";
import { rise, inView } from "../lib/motion";

export default function CTA() {
  return (
    <section id="cta" className="relative bg-paper px-5 py-24 lg:py-32">
      <motion.div
        variants={rise}
        initial="hidden"
        whileInView="show"
        viewport={inView}
        className="relative mx-auto max-w-[1100px] overflow-hidden rounded-[28px] bg-olive px-6 py-16 text-center text-cream sm:px-12 lg:py-24"
      >
        {/* layered glow + grain */}
        <div className="bg-grid pointer-events-none absolute inset-0 opacity-[0.08]" />
        <div className="animate-drift-slow pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(218,161,57,0.45),transparent_60%)] blur-2xl" />
        <div className="animate-drift pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(232,239,215,0.4),transparent_60%)] blur-2xl" />

        <div className="relative">
          <span className="eyebrow text-leaf-2">Bring your own agent</span>
          <h2 className="display mx-auto mt-5 max-w-[20ch] text-[2.5rem] leading-[1.04] sm:text-5xl lg:text-[3.6rem]">
            Point your agent at Doomberg.
          </h2>
          <p className="mx-auto mt-5 max-w-[48ch] text-[1.1rem] leading-relaxed text-cream/75">
            Connect Claude, GPT, or a custom agent over MCP. Research markets,
            backtest honestly, paper-trade on trusted infra — and replay every
            move in the glass box.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <a
              href="#"
              className="group inline-flex items-center gap-2 rounded-pill bg-cream px-7 py-3.5 text-[0.95rem] font-semibold text-olive-700 transition-all duration-300 hover:-translate-y-0.5 hover:bg-white"
            >
              Connect over MCP
              <span className="transition-transform duration-300 group-hover:translate-x-0.5">
                →
              </span>
            </a>
            <a
              href="#"
              className="inline-flex items-center gap-2 rounded-pill border border-cream/30 px-7 py-3.5 text-[0.95rem] font-semibold text-cream transition-colors duration-300 hover:bg-cream/10"
            >
              Read the docs
            </a>
          </div>
          <p className="mt-6 font-mono text-[0.72rem] uppercase tracking-[0.16em] text-cream/50">
            streamable-http · stdio · tenant-scoped tokens
          </p>
        </div>
      </motion.div>
    </section>
  );
}
