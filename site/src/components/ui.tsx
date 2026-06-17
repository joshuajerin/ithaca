import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { rise, stagger, inView } from "../lib/motion";

/* -------------------------------------------------------------------------- */
/* Reveal — drop-in scroll-reveal wrapper (fade + rise on enter).             */
/* -------------------------------------------------------------------------- */
export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "li" | "span";
}) {
  const MotionTag = motion[as];
  return (
    <MotionTag
      className={className}
      variants={rise}
      initial="hidden"
      whileInView="show"
      viewport={inView}
      transition={{ delay }}
    >
      {children}
    </MotionTag>
  );
}

/* Stagger group — children using <Reveal> or variants={rise} cascade in.     */
export function RevealGroup({
  children,
  className,
  gap = 0.08,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  gap?: number;
  delay?: number;
}) {
  return (
    <motion.div
      className={className}
      variants={stagger(gap, delay)}
      initial="hidden"
      whileInView="show"
      viewport={inView}
    >
      {children}
    </motion.div>
  );
}

/* -------------------------------------------------------------------------- */
/* Eyebrow — mono label that sits above section headings.                     */
/* -------------------------------------------------------------------------- */
export function Eyebrow({
  children,
  tone = "olive",
}: {
  children: ReactNode;
  tone?: "olive" | "muted";
}) {
  return (
    <span
      className={`eyebrow inline-flex items-center gap-2 ${
        tone === "olive" ? "text-olive" : "text-faint"
      }`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-olive" />
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Badge — the small status pill (e.g. "Real exchange data is live").         */
/* -------------------------------------------------------------------------- */
export function Badge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-pill border border-leaf-2 bg-leaf px-3.5 py-1.5 text-[0.78rem] font-medium text-olive-700">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-olive-bright opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-olive" />
      </span>
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* PillButton — primary (olive) + secondary (outline) CTAs.                   */
/* -------------------------------------------------------------------------- */
export function PillButton({
  children,
  href = "#",
  variant = "primary",
  size = "md",
}: {
  children: ReactNode;
  href?: string;
  variant?: "primary" | "secondary" | "ghost";
  size?: "md" | "lg";
}) {
  const base =
    "group inline-flex items-center gap-2 rounded-pill font-semibold transition-all duration-300 will-change-transform";
  const sizes = size === "lg" ? "px-7 py-3.5 text-[0.95rem]" : "px-5 py-2.5 text-sm";
  const variants = {
    primary:
      "bg-olive text-cream shadow-[0_1px_0_0_rgba(255,255,255,0.15)_inset,0_8px_24px_-12px_rgba(72,92,17,0.7)] hover:bg-olive-600 hover:-translate-y-0.5",
    secondary:
      "bg-leaf text-olive-700 hover:bg-leaf-2 hover:-translate-y-0.5",
    ghost:
      "border border-line-strong bg-paper/60 text-ink hover:border-olive/40 hover:bg-cream",
  };
  return (
    <a href={href} className={`${base} ${sizes} ${variants[variant]}`}>
      {children}
      <span className="transition-transform duration-300 group-hover:translate-x-0.5">
        →
      </span>
    </a>
  );
}

/* -------------------------------------------------------------------------- */
/* SectionHeader — gokite-style asymmetric header: big heading left,          */
/* descriptive copy right-aligned on desktop.                                 */
/* -------------------------------------------------------------------------- */
export function SectionHeader({
  eyebrow,
  title,
  copy,
}: {
  eyebrow: string;
  title: ReactNode;
  copy?: ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 items-end gap-6 lg:grid-cols-[1fr_minmax(0,28rem)]">
      <div>
        <Reveal>
          <Eyebrow>{eyebrow}</Eyebrow>
        </Reveal>
        <Reveal delay={0.05}>
          <h2 className="display mt-5 text-[2.4rem] leading-[1.03] text-ink sm:text-5xl lg:text-[3.4rem]">
            {title}
          </h2>
        </Reveal>
      </div>
      {copy && (
        <Reveal delay={0.1}>
          <p className="text-[1.05rem] leading-relaxed text-muted lg:text-right">
            {copy}
          </p>
        </Reveal>
      )}
    </div>
  );
}

/* Thin hairline divider used between major bands. */
export function Hairline() {
  return <div className="mx-auto h-px w-full max-w-[1200px] bg-line" />;
}
