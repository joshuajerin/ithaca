import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { CenterScrim } from './_shared';

export function Scene2() {
  const [text, setText] = useState('');
  const fullText = "Analyze NVDA's supply chain risk";

  useEffect(() => {
    let i = 0;
    const id = setInterval(() => {
      i++;
      setText(fullText.slice(0, i));
      if (i >= fullText.length) clearInterval(id);
    }, 55);
    return () => clearInterval(id);
  }, []);

  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-end z-20 pb-[20vh]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.6 }}
    >
      <CenterScrim intensity={0.7} />
      <div className="relative w-[64vw] max-w-5xl">
        <div className="flex items-center justify-center gap-3 mb-5">
          <motion.span
            className="w-2 h-2 rounded-full bg-white"
            animate={{ opacity: [1, 0.2, 1] }}
            transition={{ duration: 1.4, repeat: Infinity }}
          />
          <span
            className="font-body uppercase text-white/50 text-xs"
            style={{ letterSpacing: '0.3em' }}
          >
            Voice Mode Active
          </span>
        </div>

        <div className="border border-white/15 bg-black/70 px-10 py-7">
          <p className="font-display text-white text-center" style={{ fontSize: '2.6vw' }}>
            "{text}
            <motion.span
              animate={{ opacity: [1, 0] }}
              transition={{ duration: 0.7, repeat: Infinity }}
            >
              |
            </motion.span>
            "
          </p>
        </div>
      </div>
    </motion.div>
  );
}
