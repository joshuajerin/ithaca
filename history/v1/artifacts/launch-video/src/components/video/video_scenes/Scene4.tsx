import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';

export function Scene4() {
  const [text, setText] = useState('');
  const fullText = 'Add a 90-day volatility overlay';

  useEffect(() => {
    let i = 0;
    const id = setInterval(() => {
      i++;
      setText(fullText.slice(0, i));
      if (i >= fullText.length) clearInterval(id);
    }, 45);
    return () => clearInterval(id);
  }, []);

  return (
    <motion.div
      className="absolute inset-0 z-30 flex items-center justify-center pointer-events-none"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
    >
      <motion.div
        className="bg-black/90 border border-white/40 shadow-[0_0_36px_rgba(255,255,255,0.22)] px-9 py-7 w-[42vw] max-w-2xl"
        initial={{ scale: 0.95, opacity: 0, y: 12 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="flex items-center gap-3 mb-4">
          <span
            className="font-body uppercase text-white/50 text-[10px] font-medium"
            style={{ letterSpacing: '0.14em' }}
          >
            Refine Panel
          </span>
          <span
            className="ml-auto font-body uppercase text-white/40 text-[10px]"
            style={{ letterSpacing: '0.14em' }}
          >
            Monte Carlo Sim
          </span>
        </div>
        <p className="font-display text-white text-2xl">
          "{text}
          <motion.span
            animate={{ opacity: [1, 0] }}
            transition={{ duration: 0.7, repeat: Infinity }}
          >
            |
          </motion.span>
          "
        </p>
      </motion.div>
    </motion.div>
  );
}
