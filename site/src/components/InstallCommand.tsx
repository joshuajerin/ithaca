import { useState } from "react";
import { INSTALL_COMMAND } from "../lib/links";

type Variant = "dark" | "olive";

export default function InstallCommand({ variant = "dark" }: { variant?: Variant }) {
  const [copied, setCopied] = useState(false);

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(INSTALL_COMMAND);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = INSTALL_COMMAND;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }

    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  const shell =
    variant === "olive"
      ? "border-cream/20 bg-ink/80"
      : "border-line-strong bg-ink shadow-[0_18px_50px_-30px_rgba(24,23,15,0.6)]";
  const prompt = variant === "olive" ? "text-cream/45" : "text-faint";
  const button =
    variant === "olive"
      ? "border-cream/20 bg-cream/10 text-cream hover:bg-cream hover:text-ink"
      : "border-cream/15 bg-cream/10 text-cream hover:bg-cream hover:text-ink";

  return (
    <div className={`flex items-center gap-3 rounded-[14px] border px-3 py-2.5 text-left ${shell}`}>
      <span className={`font-mono text-[0.8rem] ${prompt}`}>$</span>
      <code className="min-w-0 flex-1 whitespace-normal break-all font-mono text-[0.8rem] leading-relaxed text-cream sm:text-[0.9rem]">
        {INSTALL_COMMAND}
      </code>
      <button
        type="button"
        onClick={copyCommand}
        className={`shrink-0 rounded-pill border px-3 py-1.5 text-[0.78rem] font-semibold transition-colors ${button}`}
        aria-label="Copy install command"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
