import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useUser } from "@clerk/react";
import type { AuthMode } from "../App";
import { EASE } from "../lib/motion";
import { APP_URL, DOCS_URL } from "../lib/links";

const LINKS = [
  { label: "Platform", href: "#platform" },
  { label: "Security", href: "#security" },
  { label: "Docs", href: DOCS_URL },
];

function Logo() {
  return (
    <a href="/" data-nav-logo className="flex items-center gap-2.5" aria-label="Ithaca home">
      {/* CSS-drawn mark: stacked layers = tools, execution, records */}
      <span className="relative grid h-7 w-7 place-items-center">
        <span className="absolute h-7 w-7 rotate-45 rounded-[7px] bg-olive" />
        <span className="absolute h-3.5 w-3.5 rotate-45 rounded-[3px] bg-leaf" />
      </span>
      <span className="text-[1.25rem] font-600 tracking-tight text-ink">
        Ithaca
      </span>
    </a>
  );
}

function NavShell({ isSignedIn }: { isSignedIn: boolean }) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.header
      initial={{ y: -24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.7, ease: EASE, delay: 0.1 }}
      className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-3.5"
    >
      <nav
        className={`flex w-full max-w-[1160px] items-center justify-between rounded-pill border px-3 py-2 transition-all duration-500 ${
          scrolled
            ? "border-line-strong bg-paper/85 shadow-[0_12px_40px_-24px_rgba(24,23,15,0.5)] backdrop-blur-xl"
            : "border-transparent bg-paper/30 backdrop-blur-sm"
        }`}
      >
        <div className="pl-2">
          <Logo />
        </div>

        <div className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="rounded-pill px-3.5 py-2 text-[0.9rem] font-medium text-ink-soft transition-colors hover:bg-cream hover:text-ink"
            >
              {l.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <a
            href={APP_URL}
            className="group inline-flex items-center gap-2 rounded-pill bg-amber px-4 py-2.5 text-[0.9rem] font-semibold text-ink shadow-[0_8px_24px_-12px_rgba(201,121,26,0.9)] transition-all duration-300 hover:-translate-y-0.5 hover:bg-amber-deep hover:text-cream"
          >
            {isSignedIn ? "Dashboard" : "Sign in"}
            <span className="transition-transform duration-300 group-hover:translate-x-0.5">
              →
            </span>
          </a>
        </div>
      </nav>
    </motion.header>
  );
}

function ClerkNav() {
  const { isLoaded, isSignedIn } = useUser();
  return <NavShell isSignedIn={isLoaded && Boolean(isSignedIn)} />;
}

export default function Nav({ authMode }: { authMode: AuthMode }) {
  if (authMode === "clerk") return <ClerkNav />;
  return <NavShell isSignedIn={false} />;
}
