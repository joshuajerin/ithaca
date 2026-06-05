import { motion } from 'framer-motion';
import { CenterScrim } from './_shared';

export function Scene1() {
  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center z-20"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.8 }}
    >
      <CenterScrim intensity={0.88} />
      <div className="relative text-center px-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          <span
            className="font-body uppercase text-white/40"
            style={{ letterSpacing: '0.45em', fontSize: '0.9vw' }}
          >
            Agentic Intelligence
          </span>
        </motion.div>

        <motion.h1
          className="font-display text-white leading-[0.95] tracking-tight my-6"
          style={{ fontSize: '7vw' }}
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, delay: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          Agentic Terminal
        </motion.h1>

        <motion.div
          className="mx-auto h-px bg-white/30"
          initial={{ width: 0 }}
          animate={{ width: '12rem' }}
          transition={{ duration: 1, delay: 1.1, ease: [0.16, 1, 0.3, 1] }}
        />

        <motion.p
          className="font-display italic text-white/70 mt-6"
          style={{ fontSize: '1.8vw' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1, delay: 1.3 }}
        >
          Synthetic Market Intelligence
        </motion.p>
      </div>
    </motion.div>
  );
}
