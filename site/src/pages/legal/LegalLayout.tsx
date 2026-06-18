import { Link } from "react-router-dom";
import Nav from "../../components/Nav";

interface Section {
  heading: string;
  content: React.ReactNode;
}

interface LegalLayoutProps {
  title: string;
  subtitle?: string;
  effectiveDate: string;
  lastUpdated: string;
  sections: Section[];
}

export default function LegalLayout({
  title,
  subtitle,
  effectiveDate,
  lastUpdated,
  sections,
}: LegalLayoutProps) {
  return (
    <div className="relative min-h-screen bg-paper">
      <Nav />
      <main className="mx-auto max-w-[72ch] px-5 pb-24 pt-28">
        {/* back link */}
        <Link
          to="/"
          className="mb-10 inline-flex items-center gap-1.5 font-mono text-[0.72rem] uppercase tracking-[0.14em] text-faint transition-colors hover:text-olive"
        >
          <span>←</span>
          <span>Back to home</span>
        </Link>

        {/* header */}
        <div className="mb-10 border-b border-line pb-8">
          <h1 className="display text-[2rem] leading-[1.15] tracking-tight text-ink">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-3 text-[1rem] leading-relaxed text-muted">{subtitle}</p>
          )}
          <div className="mt-5 flex flex-wrap gap-x-8 gap-y-1 font-mono text-[0.72rem] uppercase tracking-[0.12em] text-faint">
            <span>Effective: {effectiveDate}</span>
            <span>Last updated: {lastUpdated}</span>
          </div>
        </div>

        {/* sections */}
        <div className="space-y-10">
          {sections.map((s, i) => (
            <section key={i}>
              <h2 className="mb-3 font-mono text-[0.75rem] uppercase tracking-[0.16em] text-faint">
                {String(i + 1).padStart(2, "0")} — {s.heading}
              </h2>
              <div className="prose-legal">{s.content}</div>
            </section>
          ))}
        </div>

        {/* footer note */}
        <div className="mt-16 border-t border-line pt-8">
          <p className="text-[0.82rem] text-faint">
            Questions about these documents? Contact us at{" "}
            <a href="mailto:legal@doomberg.me" className="text-olive hover:underline">
              legal@doomberg.me
            </a>
          </p>
          <div className="mt-4 flex gap-4 font-mono text-[0.72rem] uppercase tracking-[0.14em] text-faint">
            <Link to="/legal/terms" className="hover:text-olive">Terms</Link>
            <Link to="/legal/privacy" className="hover:text-olive">Privacy</Link>
            <Link to="/legal/disclosures" className="hover:text-olive">Disclosures</Link>
            <Link to="/legal/data-sources" className="hover:text-olive">Data Sources</Link>
          </div>
        </div>
      </main>
    </div>
  );
}
