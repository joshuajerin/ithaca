import { useEffect } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Nav from "../components/Nav";
import Footer from "../components/Footer";
import { EFFECTIVE_DATE, LAST_UPDATED, LEGAL_DOCS, getLegalDoc } from "./registry";

// Markdown element → Tailwind class map. Keeps the legal prose on the site's
// warm ink/olive/cream palette without pulling in the typography plugin.
const mdComponents = {
  h1: () => null, // the page header renders the title; skip the doc's own H1
  h2: (props: any) => (
    <h2 className="mt-12 mb-3 text-[1.4rem] font-600 tracking-tight text-ink" {...props} />
  ),
  h3: (props: any) => (
    <h3 className="mt-8 mb-2 text-[1.1rem] font-600 text-ink" {...props} />
  ),
  p: (props: any) => (
    <p className="my-4 text-[0.98rem] leading-relaxed text-ink-soft" {...props} />
  ),
  ul: (props: any) => (
    <ul className="my-4 list-disc space-y-2 pl-6 text-[0.98rem] leading-relaxed text-ink-soft" {...props} />
  ),
  ol: (props: any) => (
    <ol className="my-4 list-decimal space-y-2 pl-6 text-[0.98rem] leading-relaxed text-ink-soft" {...props} />
  ),
  li: (props: any) => <li className="pl-1" {...props} />,
  a: ({ href = "", ...props }: any) =>
    href.startsWith("/") ? (
      <Link to={href} className="text-olive underline underline-offset-2 hover:text-olive-700" {...props} />
    ) : (
      <a href={href} className="text-olive underline underline-offset-2 hover:text-olive-700" {...props} />
    ),
  strong: (props: any) => <strong className="font-600 text-ink" {...props} />,
  blockquote: (props: any) => (
    <blockquote
      className="my-6 rounded-[10px] border border-line-strong bg-cream/60 px-5 py-4 text-[0.9rem] leading-relaxed text-muted"
      {...props}
    />
  ),
  code: (props: any) => (
    <code className="rounded-[5px] bg-cream px-1.5 py-0.5 font-mono text-[0.82rem] text-olive-700" {...props} />
  ),
  table: (props: any) => (
    <div className="my-6 overflow-x-auto">
      <table className="w-full border-collapse text-left text-[0.9rem] text-ink-soft" {...props} />
    </div>
  ),
  thead: (props: any) => <thead className="border-b border-line-strong" {...props} />,
  th: (props: any) => (
    <th className="px-3 py-2 font-mono text-[0.72rem] uppercase tracking-[0.1em] text-faint" {...props} />
  ),
  td: (props: any) => <td className="border-b border-line px-3 py-2 align-top" {...props} />,
  hr: () => <hr className="my-10 border-line" />,
};

export default function LegalPage({ slug }: { slug: string }) {
  const doc = getLegalDoc(slug);

  // Reset scroll when navigating between legal docs.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [slug]);

  // Keep the document title in sync for sharing / SEO.
  useEffect(() => {
    document.title = doc ? `${doc.title} · Doomberg` : "Not found · Doomberg";
    return () => {
      document.title = "Doomberg";
    };
  }, [doc]);

  return (
    <div className="relative min-h-screen bg-paper">
      <Nav />
      <main className="mx-auto max-w-[820px] px-5 pb-24 pt-32">
        {/* breadcrumb — reliable home/legal navigation regardless of Nav anchors */}
        <nav className="mb-8 font-mono text-[0.72rem] uppercase tracking-[0.14em] text-faint">
          <Link to="/" className="hover:text-olive">
            Doomberg
          </Link>
          <span className="px-2">/</span>
          <span className="text-muted">Legal</span>
          {doc ? (
            <>
              <span className="px-2">/</span>
              <span className="text-ink">{doc.title}</span>
            </>
          ) : null}
        </nav>

        {doc ? (
          <article>
            <header className="border-b border-line pb-6">
              <h1 className="text-[2.1rem] font-600 leading-tight tracking-tight text-ink">
                {doc.title}
              </h1>
              <p className="mt-3 font-mono text-[0.78rem] uppercase tracking-[0.12em] text-faint">
                Effective {EFFECTIVE_DATE} · Last updated {LAST_UPDATED}
              </p>
            </header>

            <div className="mt-6">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                {doc.body}
              </ReactMarkdown>
            </div>
          </article>
        ) : (
          <div className="py-16">
            <h1 className="text-[2rem] font-600 text-ink">Document not found</h1>
            <p className="mt-3 text-ink-soft">
              That legal document doesn't exist.{" "}
              <Link to="/" className="text-olive underline underline-offset-2">
                Return home
              </Link>
              .
            </p>
          </div>
        )}

        {/* index of the other legal documents */}
        <aside className="mt-16 border-t border-line pt-8">
          <h2 className="font-mono text-[0.72rem] uppercase tracking-[0.14em] text-faint">
            More legal documents
          </h2>
          <ul className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {LEGAL_DOCS.filter((d) => d.slug !== slug).map((d) => (
              <li key={d.slug}>
                <Link
                  to={`/${d.slug}`}
                  className="text-[0.92rem] text-ink-soft transition-colors hover:text-olive"
                >
                  {d.title}
                </Link>
              </li>
            ))}
          </ul>
        </aside>
      </main>
      <Footer />
    </div>
  );
}
