import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="border-t border-line bg-cream/50">
      <div className="mx-auto max-w-[1200px] px-5 py-6">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <Link to="/" className="flex items-center gap-2 text-[1.1rem] font-600 tracking-tight text-ink hover:text-olive">
            <img src="/ithaca-mark.svg" width="24" height="24" alt="Ithaca" />
            <span>Ithaca</span>
          </Link>
          <nav aria-label="Legal" className="flex items-center gap-4 text-[0.82rem] text-ink-soft">
            <Link to="/terms" className="transition-colors hover:text-olive">
              Terms
            </Link>
            <Link to="/privacy" className="transition-colors hover:text-olive">
              Privacy
            </Link>
          </nav>
        </div>

        <div className="mt-4 border-t border-line pt-4">
          <p className="text-[0.82rem] text-faint">
            © 2026 Ithaca. Research &amp; paper-trading platform, not investment advice.
          </p>
        </div>
      </div>
    </footer>
  );
}
