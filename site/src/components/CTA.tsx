import { motion } from "framer-motion";
import { rise, inView } from "../lib/motion";
import InstallCommand from "./InstallCommand";

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
        {/* layered glow + film grain (subtle, on the dark olive band) */}
        <div className="bg-grid pointer-events-none absolute inset-0 opacity-[0.08]" />
        <div className="bg-grain pointer-events-none absolute inset-0 mix-blend-overlay" />
        <div className="animate-drift-slow pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(239,159,42,0.5),transparent_60%)] blur-2xl" />
        <div className="animate-drift pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(232,239,215,0.4),transparent_60%)] blur-2xl" />

        <div className="relative">
          <h2 className="display mx-auto max-w-[20ch] text-[2.5rem] leading-[1.04] sm:text-5xl lg:text-[3.6rem]">
            Open Doomberg.
          </h2>
          <p className="mx-auto mt-5 max-w-[48ch] text-[1.1rem] leading-relaxed text-cream/75">
            Use the dashboard for market data, backtests, and paper trades.
          </p>
          <div className="mx-auto mt-9 max-w-[760px]">
            <InstallCommand variant="olive" />
          </div>
        </div>
      </motion.div>
    </section>
  );
}
