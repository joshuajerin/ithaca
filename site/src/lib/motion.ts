import type { Variants } from "framer-motion";

// Shared easing — the soft "settle" curve used across all reveals.
export const EASE = [0.22, 1, 0.36, 1] as const;

// Fade + rise. The workhorse scroll-reveal for headings, paragraphs, cards.
export const rise: Variants = {
  hidden: { opacity: 0, y: 26 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.7, ease: EASE },
  },
};

// Stagger container: children animate in sequence as the group enters view.
export const stagger = (gap = 0.08, delay = 0): Variants => ({
  hidden: {},
  show: {
    transition: { staggerChildren: gap, delayChildren: delay },
  },
});

// Scale-in for visual/figure blocks.
export const popIn: Variants = {
  hidden: { opacity: 0, y: 32, scale: 0.97 },
  show: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.8, ease: EASE },
  },
};

// Viewport config reused everywhere so reveals feel consistent.
export const inView = { once: true, margin: "-12% 0px -12% 0px" } as const;
