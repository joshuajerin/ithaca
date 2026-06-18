import { motion } from 'framer-motion';

export function VoiceOrb({
  active,
  visible = true,
  scale = 1,
  x = 0,
  y = 0,
}: {
  active: boolean;
  visible?: boolean;
  scale?: number;
  x?: number | string;
  y?: number | string;
}) {
  return (
    <motion.div
      className="absolute top-0 left-0 w-32 h-32 flex items-center justify-center z-10 pointer-events-none"
      animate={{ x, y, scale, opacity: visible ? 1 : 0 }}
      transition={{
        x: { type: 'spring', stiffness: 120, damping: 26 },
        y: { type: 'spring', stiffness: 120, damping: 26 },
        scale: { type: 'spring', stiffness: 120, damping: 26 },
        opacity: { duration: 0.6 },
      }}
      style={{ translateX: '-50%', translateY: '-50%' }}
    >
      <motion.div
        className="absolute inset-0 rounded-full border border-white/20"
        animate={{
          scale: active ? [1, 1.8, 1] : 1,
          opacity: active ? [0.55, 0, 0.55] : 0.2,
        }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute inset-2 rounded-full border border-white/40"
        animate={{
          scale: active ? [1, 1.4, 1] : 1,
          opacity: active ? [0.8, 0, 0.8] : 0.4,
        }}
        transition={{ duration: 2.4, delay: 0.4, repeat: Infinity, ease: 'easeInOut' }}
      />

      <motion.div
        className="w-16 h-16 rounded-full"
        style={{
          background:
            'radial-gradient(circle at 30% 30%, rgba(255,255,255,0.98), rgba(120,120,120,0.25))',
          boxShadow: '0 0 40px rgba(255,255,255,0.3), inset 0 0 20px rgba(255,255,255,0.8)',
        }}
        animate={{ scale: active ? [1, 1.12, 1] : [1, 1.03, 1] }}
        transition={{
          duration: active ? 1.4 : 4,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />
    </motion.div>
  );
}
