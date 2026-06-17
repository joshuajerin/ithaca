import { motion } from "framer-motion";
import { SectionHeader } from "./ui";
import { rise, stagger, inView } from "../lib/motion";

const STACK = [
  {
    layer: "Layer 1",
    name: "Direct exchange feeds",
    desc: "Nasdaq TotalView-ITCH, NYSE Pillar/XDP, Cboe PITCH — raw, per-venue, un-normalized depth-of-book straight off the matching engine.",
    note: "the colo endgame, not a launch requirement",
    fill: "bg-olive text-cream",
    w: "w-full",
  },
  {
    layer: "Layer 2",
    name: "Consolidated SIP tapes",
    desc: "CTA/UTP NBBO — the regulated public price, Level 1, aggregated across venues. Broker-grade SIP backs paper-live fills.",
    note: "via Alpaca",
    fill: "bg-leaf text-olive-700",
    w: "w-[88%]",
  },
  {
    layer: "Layer 3",
    name: "Normalized professional feeds",
    desc: "One pre-normalized stream across hundreds of venues — the way Bloomberg B-PIPE actually delivers. Databento for direct-feed prices & order book.",
    note: "via Databento",
    fill: "bg-sand text-ink",
    w: "w-[76%]",
  },
  {
    layer: "Research",
    name: "Point-in-time history",
    desc: "Survivorship-bias-free, vintaged fundamentals — the single highest-leverage purchase. It unblocks honest fundamental-factor backtesting.",
    note: "via Sharadar",
    fill: "bg-cream-2 text-ink border border-line-strong",
    w: "w-[64%]",
  },
];

export default function DataSourcing() {
  return (
    <section id="data" className="relative bg-cream/40 py-24 lg:py-32">
      <div className="mx-auto max-w-[1200px] px-5">
        <SectionHeader
          eyebrow="Real data"
          title={
            <>
              Sourced the way
              <br className="hidden sm:block" /> the desks do it
            </>
          }
          copy="No survivorship-biased free feeds. We buy from the vendors that take the direct exchange feeds — and treat self-operated colo ticker plants as a graduation trigger, not a launch cost."
        />

        <motion.div
          variants={stagger(0.1)}
          initial="hidden"
          whileInView="show"
          viewport={inView}
          className="mt-12 flex flex-col items-start gap-3"
        >
          {STACK.map((s) => (
            <motion.div
              key={s.name}
              variants={rise}
              className={`${s.w} ${s.fill} overflow-hidden rounded-2xl p-6 shadow-[0_24px_60px_-45px_rgba(24,23,15,0.6)] transition-transform duration-300 hover:translate-x-1`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-[0.72rem] uppercase tracking-[0.14em] opacity-70">
                    {s.layer}
                  </span>
                  <h3 className="text-xl">{s.name}</h3>
                </div>
                <span className="rounded-pill bg-black/10 px-3 py-1 font-mono text-[0.7rem]">
                  {s.note}
                </span>
              </div>
              <p className="mt-2 max-w-[60ch] text-[0.95rem] leading-relaxed opacity-85">
                {s.desc}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
