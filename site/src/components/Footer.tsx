import { Link } from "react-router-dom";
import { DOCS_URL } from "../lib/links";

type FooterLink = { label: string; to?: string; href?: string };

const COLUMNS: { heading: string; links: FooterLink[] }[] = [
  {
    heading: "Platform",
    links: [
      { label: "MCP gateway" },
      { label: "Tools catalog" },
      { label: "Glass box" },
      { label: "Boards" },
      { label: "Pricing" },
    ],
  },
  {
    heading: "Build",
    links: [
      { label: "Docs", href: DOCS_URL },
      { label: "StrategySpec" },
      { label: "API reference" },
      { label: "Status" },
      { label: "Changelog" },
    ],
  },
  {
    heading: "Company",
    links: [
      { label: "About" },
      { label: "Architecture" },
      { label: "Security" },
      { label: "Careers" },
      { label: "Blog" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { label: "Terms", to: "/terms" },
      { label: "Privacy", to: "/privacy" },
      { label: "Cookies", to: "/cookies" },
      { label: "Acceptable use", to: "/acceptable-use" },
      { label: "Disclosures", to: "/disclosures" },
      { label: "Data sources", to: "/data-sources" },
      { label: "Subprocessors", to: "/subprocessors" },
    ],
  },
];

const linkClass =
  "text-[0.92rem] text-ink-soft transition-colors hover:text-olive";

export default function Footer() {
  return (
    <footer className="border-t border-line bg-cream/50">
      <div className="mx-auto max-w-[1200px] px-5 py-16">
        <div className="grid grid-cols-2 gap-10 sm:grid-cols-3 lg:grid-cols-6">
          <div className="col-span-2">
            <div className="flex items-center gap-2.5">
              <span className="relative grid h-7 w-7 place-items-center">
                <span className="absolute h-7 w-7 rotate-45 rounded-[7px] bg-olive" />
                <span className="absolute h-3.5 w-3.5 rotate-45 rounded-[3px] bg-leaf" />
              </span>
              <span className="text-[1.25rem] font-600 tracking-tight text-ink">
                Doomberg
              </span>
            </div>
            <p className="mt-4 max-w-[34ch] text-[0.92rem] leading-relaxed text-muted">
              The quant tool-platform your agent thinks with. Vetted tools over
              MCP, declarative execution on trusted infra, and a glass box that
              records everything.
            </p>
            <div className="mt-5 flex gap-2">
              {["MCP", "REST", "SSE"].map((t) => (
                <span
                  key={t}
                  className="rounded-pill border border-line bg-paper px-3 py-1 font-mono text-[0.7rem] text-faint"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.heading}>
              <h4 className="font-mono text-[0.72rem] uppercase tracking-[0.14em] text-faint">
                {col.heading}
              </h4>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.label}>
                    {l.to ? (
                      <Link to={l.to} className={linkClass}>
                        {l.label}
                      </Link>
                    ) : l.href ? (
                      <a href={l.href} className={linkClass}>
                        {l.label}
                      </a>
                    ) : (
                      <a href="#" className={linkClass}>
                        {l.label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-14 flex flex-col items-start justify-between gap-4 border-t border-line pt-7 sm:flex-row sm:items-center">
          <p className="text-[0.82rem] text-faint">
            © {new Date().getFullYear()} Doomberg. Research & paper-trading platform, not investment advice.
          </p>
          <p className="font-mono text-[0.72rem] uppercase tracking-[0.14em] text-faint">
            Never runs your agent · Never executes agent code
          </p>
        </div>
      </div>
    </footer>
  );
}
