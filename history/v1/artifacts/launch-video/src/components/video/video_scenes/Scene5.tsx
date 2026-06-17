import { motion } from 'framer-motion';
import { CenterScrim } from './_shared';

export function Scene5() {
  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-end z-20 pb-[16vh]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.6 }}
    >
      <CenterScrim intensity={0.62} />
      <div className="relative flex flex-col items-center gap-7">
        <div className="flex items-end gap-1.5 h-12">
          {[...Array(28)].map((_, i) => (
            <motion.span
              key={i}
              className="w-1 h-12 bg-white/70 origin-bottom"
              animate={{ scaleY: [0.18, 1, 0.4, 0.8, 0.22] }}
              transition={{
                duration: 1.3,
                repeat: Infinity,
                delay: i * 0.045,
                ease: 'easeInOut',
              }}
            />
          ))}
        </div>

        <div className="text-center">
          <p className="font-display text-white mb-2" style={{ fontSize: '2.4vw' }}>
            Hands-free, always listening
          </p>
          <span
            className="font-body uppercase text-white/50 text-xs"
            style={{ letterSpacing: '0.3em' }}
          >
            Voice Orb · Real-time Response
          </span>
        </div>
      </div>
    </motion.div>
  );
}
