// Canonical legal-document registry. Each entry maps a URL slug to its title and
// raw Markdown body (imported via Vite's `?raw`). The Markdown files in
// ../content/legal are the single source of truth — the web app links to the
// deployed URLs of these pages rather than re-rendering the content.

import termsBody from "../content/legal/terms.md?raw";
import privacyBody from "../content/legal/privacy.md?raw";
import cookiesBody from "../content/legal/cookies.md?raw";
import acceptableUseBody from "../content/legal/acceptable-use.md?raw";
import disclosuresBody from "../content/legal/disclosures.md?raw";
import dataSourcesBody from "../content/legal/data-sources.md?raw";
import subprocessorsBody from "../content/legal/subprocessors.md?raw";

export type LegalDoc = {
  slug: string;
  title: string;
  body: string;
};

// Shared effective / last-updated date for the published legal documents.
export const EFFECTIVE_DATE = "July 13, 2026";
export const LAST_UPDATED = "July 13, 2026";

// Ordered so the in-page index renders in a sensible reading order.
export const LEGAL_DOCS: LegalDoc[] = [
  { slug: "terms", title: "Terms of Service", body: termsBody },
  { slug: "privacy", title: "Privacy Policy", body: privacyBody },
  { slug: "cookies", title: "Cookie Policy", body: cookiesBody },
  { slug: "acceptable-use", title: "Acceptable Use Policy", body: acceptableUseBody },
  { slug: "disclosures", title: "Risk Disclosures & Disclaimers", body: disclosuresBody },
  { slug: "data-sources", title: "Third-Party Data Sources", body: dataSourcesBody },
  { slug: "subprocessors", title: "Subprocessors", body: subprocessorsBody },
];

export function getLegalDoc(slug: string): LegalDoc | undefined {
  return LEGAL_DOCS.find((d) => d.slug === slug);
}
