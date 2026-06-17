import { motion } from 'framer-motion';

const CATEGORIES = [
  { k: '01', t: 'Quant & Risk', d: 'Monte Carlo · VaR · Factors' },
  { k: '02', t: 'Fundamentals', d: 'DCF · Cash Flow · Multiples' },
  { k: '03', t: 'Fixed Income', d: 'Yield Curves · Duration' },
  { k: '04', t: 'Macro', d: 'Rates · Inflation · Growth' },
  { k: '05', t: 'Execution', d: 'Order Book · Liquidity' },
  { k: '06', t: 'Sentiment', d: 'News · Flow · Positioning' },
];

export function Scene6() {
  return (
    <motion.div
      className="absolute inset-0 z-30 flex flex-col items-center justify-center px-[8vw]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.6 }}
    >
      <div className="absolute inset-0 bg-black/88" />

      <motion.div
        className="relative text-center mb-10"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        <span
          className="font-body uppercase text-white/40 text-xs"
          style={{ letterSpacing: '0.4em' }}
        >
          One terminal · Every discipline
        </span>
      </motion.div>

      <div className="relative grid grid-cols-3 gap-px bg-white/10 w-full max-w-6xl">
        {CATEGORIES.map((c, i) => (
          <motion.div
            key={c.k}
            className="bg-black p-7 flex flex-col gap-2"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + i * 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          >
            <span
              className="font-body text-white/30 text-xs"
              style={{ letterSpacing: '0.14em' }}
            >
              {c.k}
            </span>
            <h3 className="font-display text-white text-2xl leading-none">{c.t}</h3>
            <span
              className="font-body uppercase text-white/45 text-[10px]"
              style={{ letterSpacing: '0.14em' }}
            >
              {c.d}
            </span>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
