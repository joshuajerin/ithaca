import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { useEffect, useState } from "react";
import { EASE } from "../lib/motion";
import { Badge, PillButton } from "./ui";
import IsometricStack from "./IsometricStack";
import { APP_URL } from "../lib/links";

// Three layers top→bottom: Data / Deploy / Observe (index matches stack slab order).
const N_LAYERS = 3;

function HeroBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="bg-hero-warm absolute inset-0" />
      <div className="absolute left-[28%] top-[46%] h-[42rem] w-[62rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(ellipse_at_center,rgba(243,237,222,0.7),rgba(243,237,222,0.28)_46%,transparent_72%)] blur-2xl" />
      <div className="bg-grid absolute inset-x-0 top-0 h-1/2 opacity-25 [mask-image:linear-gradient(to_bottom,#000,transparent)]" />
      <div className="bg-grain-strong absolute inset-0 mix-blend-overlay" />
      <div className="bg-grain absolute inset-0 mix-blend-soft-light" />
      <div className="bg-grain absolute inset-0 opacity-[0.14] mix-blend-multiply" />
      <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-black/10" />
    </div>
  );
}

export default function Hero() {
  // null = all layers shown (cursor not over stack); 0/1/2 = isolate that slab.
  const [active, setActive] = useState<number | null>(null);
  void N_LAYERS; // used implicitly via the 3 raw/spring values below

  // Spring-smoothed focus values for each layer — 1 when active, 0 when not.
  const raw0 = useMotionValue(1);
  const raw1 = useMotionValue(0);
  const raw2 = useMotionValue(0);
  const raws = [raw0, raw1, raw2];

  const f0 = useSpring(raw0, { stiffness: 160, damping: 28 });
  const f1 = useSpring(raw1, { stiffness: 160, damping: 28 });
  const f2 = useSpring(raw2, { stiffness: 160, damping: 28 });
  // null = all shown; number = isolate that layer, remove others.
  useEffect(() => {
    raws.forEach((mv, i) => mv.set(active === null ? 1 : i === active ? 1 : 0));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const separation = useMotionValue(0.72);

  // Blend the focus springs into the stack's top/mid/bot inputs.
  // Stack order: top=Data(0), mid=Deploy(1), bot=Observe(2).
  const focusTop = useTransform(f0, (v) => v);
  const focusMid = useTransform(f1, (v) => v);
  const focusBot = useTransform(f2, (v) => v);

  const container = {
    hidden: {},
    show: { transition: { staggerChildren: 0.09, delayChildren: 0.12 } },
  };
  const item = {
    hidden: { opacity: 0, y: 22 },
    show: { opacity: 1, y: 0, transition: { duration: 0.8, ease: EASE } },
  };

  return (
    <section
      id="top"
      className="relative isolate flex min-h-[82svh] items-center overflow-hidden pb-16 pt-28 sm:pt-32 lg:pb-10 lg:pt-26"
    >
      <HeroBackdrop />

      <div className="relative mx-auto grid w-full max-w-[1260px] grid-cols-1 items-center gap-8 px-5 lg:grid-cols-[1.1fr_0.9fr] lg:gap-4">
        {/* LEFT — header + interactive layer legend */}
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="text-center lg:text-left"
        >
          <motion.div variants={item} className="flex justify-center lg:justify-start">
            <Badge>Real exchange-grade data is live</Badge>
          </motion.div>

          <motion.h1
            variants={item}
            className="display mx-auto mt-6 max-w-[15ch] text-[2.85rem] leading-[1.0] text-ink sm:text-[3.5rem] lg:mx-0 lg:text-[4.2rem] lg:leading-[0.98]"
          >
            The tool-platform for the agent economy
          </motion.h1>

          <motion.p
            variants={item}
            className="mx-auto mt-5 max-w-[44ch] text-[1.05rem] leading-relaxed text-muted sm:text-[1.15rem] lg:mx-0"
          >
            Doomberg gives autonomous agents vetted market tools, honest
            backtesting, and paper-trading on trusted infrastructure — recorded
            in a replayable glass box.
          </motion.p>


          <motion.div
            variants={item}
            className="mt-7 flex flex-wrap items-center justify-center gap-3 lg:justify-start"
          >
            <PillButton href={APP_URL} variant="primary" size="lg">
              Connect over MCP
            </PillButton>
            <PillButton href="#features" variant="secondary" size="lg">
              Explore the platform
            </PillButton>
          </motion.div>

          <motion.p
            variants={item}
            className="mt-5 font-mono text-[0.72rem] uppercase tracking-[0.16em] text-gold-deep"
          >
            Never runs your agent · Never executes agent-authored code
          </motion.p>
        </motion.div>

        {/* RIGHT — isometric stack; cursor position over the stack drives layer focus */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, ease: EASE, delay: 0.3 }}
          className="relative flex items-center justify-center lg:justify-end"
        >
          <div
            className="w-full max-w-[420px] lg:max-w-[440px]"
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const y = (e.clientY - rect.top) / rect.height;
              // Stack visually reads top→bottom as Data→Deploy→Observe in screen space.
              // Divide the container into thirds to pick the nearest slab.
              if (y < 0.38) setActive(0);        // Data (top slab)
              else if (y < 0.68) setActive(1);   // Deploy (mid slab)
              else setActive(2);                  // Observe (bottom slab)
            }}
            onMouseLeave={() => setActive(null)}
          >
            <IsometricStack
              focus={{ top: focusTop, mid: focusMid, bot: focusBot }}
              separation={separation}
              idle
            />
          </div>
        </motion.div>
      </div>
    </section>
  );
}
