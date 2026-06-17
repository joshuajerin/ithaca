import { motion } from "framer-motion";
import { SectionHeader } from "./ui";
import { rise, stagger, inView } from "../lib/motion";

type Cap = {
  title: string;
  body: string;
  tag: string;
  span?: string; // grid span classes
  feature?: boolean;
};

const CAPS: Cap[] = [
  {
    title: "No-lookahead backtesting",
    body: "Point-in-time windows, walk-forward, Monte Carlo. Every run ships deflated Sharpe + PBO/CSCV overfitting diagnostics by default — honesty isn't optional.",
    tag: "backtest.run",
    span: "lg:col-span-2 lg:row-span-2",
    feature: true,
  },
  {
    title: "Multi-factor risk model",
    body: "Pure-numpy factor exposures, stress tests, scenario shocks, portfolio VaR.",
    tag: "risk.model",
  },
  {
    title: "Execution sim & TCA",
    body: "Realized vs. modeled separation, no fake volume — ever. Slippage you can defend.",
    tag: "tca.report",
  },
  {
    title: "Point-in-time data",
    body: "Survivorship-bias-free history with vintaged as-of truncation. PIT is a per-source capability flag, never manufactured.",
    tag: "asOf",
    span: "lg:col-span-2",
  },
  {
    title: "Pre-trade compliance gate",
    body: "Gross/net/per-name caps and restricted lists, re-checked after projection.",
    tag: "gate.evaluate",
  },
  {
    title: "Order-book replay",
    body: "IEX DEEP venue-only reconstruction, T+1. Real depth, never synthesized.",
    tag: "orderbook.replay",
  },
  {
    title: "Portfolio construction",
    body: "Mean-variance and risk-parity optimizers with cost-aware rebalancing plans.",
    tag: "portfolio.optimize",
  },
  {
    title: "Alt-data feeds",
    body: "Congressional trades, Form 4/5 insider clusters, ETF holdings & reverse exposure, earnings calendar, SEC full-text filings, FRED/ALFRED releases.",
    tag: "ideas.stream",
    span: "lg:col-span-2",
  },
];

export default function Capabilities() {
  return (
    <section id="capabilities" className="relative bg-paper py-24 lg:py-32">
      <div className="mx-auto max-w-[1200px] px-5">
        <SectionHeader
          eyebrow="Capabilities"
          title={
            <>
              The desk, as <br className="hidden sm:block" />
              callable tools
            </>
          }
          copy="Roughly eighty quant and data renderers from the original terminal, reborn as tool outputs your agent can request — each one a question it asks, with a panel for the answer."
        />

        <motion.div
          variants={stagger(0.07)}
          initial="hidden"
          whileInView="show"
          viewport={inView}
          className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 lg:auto-rows-[minmax(0,1fr)]"
        >
          {CAPS.map((c) => (
            <motion.article
              key={c.title}
              variants={rise}
              className={`group relative flex flex-col overflow-hidden rounded-[18px] border border-line bg-cream/30 p-6 transition-colors duration-300 hover:border-olive/30 hover:bg-cream/60 ${
                c.span ?? ""
              }`}
            >
              {c.feature && <FeatureGlyph />}
              <div className="relative flex flex-1 flex-col">
                <span className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-olive">
                  {c.tag}
                </span>
                <h3
                  className={`mt-3 text-ink ${
                    c.feature ? "text-[1.7rem] leading-tight" : "text-xl"
                  }`}
                >
                  {c.title}
                </h3>
                <p className="mt-3 text-[0.95rem] leading-relaxed text-muted">
                  {c.body}
                </p>
                <span className="mt-auto pt-5 text-olive opacity-0 transition-opacity duration-300 group-hover:opacity-100">
                  →
                </span>
              </div>
            </motion.article>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

// A decorative rising-bars glyph for the feature card.
function FeatureGlyph() {
  return (
    <div className="pointer-events-none absolute -right-6 -top-6 flex h-40 w-40 items-end justify-center gap-1.5 opacity-[0.13]">
      {[40, 70, 55, 90, 65, 100].map((h, i) => (
        <span
          key={i}
          className="w-3.5 rounded-t bg-olive"
          style={{ height: `${h}%` }}
        />
      ))}
    </div>
  );
}
