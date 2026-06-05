import { motion } from 'framer-motion';

export function Scene7() {
  return (
    <motion.div
      className="absolute inset-0 bg-black flex flex-col items-center justify-center z-50"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.8 }}
    >
      <motion.div
        className="flex flex-col items-center gap-8"
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 0.3, duration: 1, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="w-14 h-14 border-2 border-white rotate-45 flex items-center justify-center">
          <div className="w-6 h-6 bg-white/20 -rotate-45" />
        </div>

        <div className="text-center">
          <h2 className="font-display text-white tracking-tight leading-none" style={{ fontSize: '4vw' }}>
            Agentic Terminal
          </h2>
          <p
            className="font-body uppercase text-white/50 text-sm mt-4"
            style={{ letterSpacing: '0.3em' }}
          >
            Synthetic Market Intelligence
          </p>
        </div>

        <motion.div
          className="mt-4 border border-white/30 px-8 py-3"
          initial={{ y: 16, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 1.4, duration: 0.8 }}
        >
          <span
            className="font-body uppercase text-white text-sm"
            style={{ letterSpacing: '0.25em' }}
          >
            Available Now
          </span>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
