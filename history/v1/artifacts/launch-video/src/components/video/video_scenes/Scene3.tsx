import { motion } from 'framer-motion';

export function Scene3() {
  return (
    <motion.div
      className="absolute inset-x-0 bottom-0 z-30 flex justify-center pb-8 pointer-events-none"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
    >
      <motion.div
        className="bg-black/85 border border-white/15 px-7 py-3"
        initial={{ y: 30, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 1.4, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      >
        <span
          className="font-body uppercase text-white/70 text-xs"
          style={{ letterSpacing: '0.25em' }}
        >
          AI composes a live dashboard in seconds
        </span>
      </motion.div>
    </motion.div>
  );
}
