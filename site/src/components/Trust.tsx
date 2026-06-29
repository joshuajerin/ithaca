import { motion } from "framer-motion";
import { rise, stagger, inView } from "../lib/motion";

const PILLARS = [
  {
    k: "01",
    t: "Never runs your agent",
    b: "Doomberg exposes tools and executes declarative specs. It never runs the agent loop and never executes agent-authored code — the exact path that produced v1's two critical RCEs is gone.",
  },
  {
    k: "02",
    t: "Strategies are data, not code",
    b: "A StrategySpec is a closed, validated schema checked against the operator registry. There is no free-form code field to guard-then-trust. Renderers are a closed, vendored set.",
  },
  {
    k: "03",
    t: "One writer on the money path",
    b: "Workers propose book deltas; the control plane applies them in a serialized transaction and re-checks gross exposure after projection. Backtest math is paper math, by construction.",
  },
  {
    k: "04",
    t: "Tenant isolation as an invariant",
    b: "firmId is derived once at the front door and enforced in the data layer with Postgres RLS. The UI can't pass it and can't widen it. Every read is implicitly scoped.",
  },
  {
    k: "05",
    t: "Aggregate deadlines, visible",
    b: "Sessions carry a wall-clock deadline and credit budget — not just per-call timeouts. A runaway run is obvious in the header, not buried in spinners.",
  },
  {
    k: "06",
    t: "Honest by default",
    b: "Every backtest emits deflated Sharpe and PBO/CSCV. Provenance — source, as-of, freshness, PIT, coverage, cost — rides on every tool result. The event log is the audit trail.",
  },
];

export default function Trust() {
  return (
    <section id="security" className="relative overflow-hidden bg-olive-700 py-24 text-cream lg:py-32">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-[0.07]" />
      <div className="bg-grain pointer-events-none absolute inset-0 mix-blend-overlay" />
      <div className="pointer-events-none absolute -left-40 top-0 h-[36rem] w-[36rem] rounded-full bg-[radial-gradient(circle,rgba(111,143,26,0.5),transparent_60%)] blur-3xl" />
      <div className="pointer-events-none absolute -right-40 bottom-0 h-[34rem] w-[34rem] rounded-full bg-[radial-gradient(circle,rgba(239,159,42,0.3),transparent_60%)] blur-3xl" />

      <div className="relative mx-auto max-w-[1200px] px-5">
        <div className="max-w-[34rem]">
          <motion.span
            variants={rise}
            initial="hidden"
            whileInView="show"
            viewport={inView}
            className="eyebrow inline-flex items-center gap-2 text-leaf-2"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-leaf" />
            Trust & safety
          </motion.span>
          <motion.h2
            variants={rise}
            initial="hidden"
            whileInView="show"
            viewport={inView}
            transition={{ delay: 0.05 }}
            className="display mt-5 text-[2.4rem] leading-[1.04] sm:text-5xl lg:text-[3.4rem]"
          >
            A platform you can hand an
            <span className="text-leaf"> untrusted agent.</span>
          </motion.h2>
          <motion.p
            variants={rise}
            initial="hidden"
            whileInView="show"
            viewport={inView}
            transition={{ delay: 0.1 }}
            className="mt-6 text-[1.08rem] leading-relaxed text-cream/70"
          >
            v2 assumes the agent is external and untrusted. The architecture is
            built so that even a hostile agent can read, propose, and be
            recorded — but never run code, move money, or cross a tenant line.
          </motion.p>
        </div>

        <motion.div
          variants={stagger(0.08)}
          initial="hidden"
          whileInView="show"
          viewport={inView}
          className="mt-14 grid grid-cols-1 gap-px overflow-hidden rounded-[20px] border border-cream/15 bg-cream/10 sm:grid-cols-2 lg:grid-cols-3"
        >
          {PILLARS.map((p) => (
            <motion.div
              key={p.k}
              variants={rise}
              className="group bg-olive-700 p-7 transition-colors duration-300 hover:bg-olive-600"
            >
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-[0.78rem] text-gold">{p.k}</span>
                <h3 className="text-xl text-cream">{p.t}</h3>
              </div>
              <p className="mt-3 text-[0.94rem] leading-relaxed text-cream/65">
                {p.b}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
