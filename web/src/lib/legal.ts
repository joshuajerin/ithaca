// Legal/policy links. The canonical legal documents live on the marketing site
// (site/), so the app links out to those public URLs rather than re-rendering them.
// Override the base with VITE_SITE_URL (e.g. https://tradeithaca.com).

export const SITE_URL: string =
  (import.meta.env.VITE_SITE_URL as string | undefined)?.replace(/\/$/, "") ??
  "https://tradeithaca.com";

export const legalUrl = (slug: string): string => `${SITE_URL}/${slug}`;

export const LEGAL_LINKS: { label: string; slug: string }[] = [
  { label: "Terms", slug: "terms" },
  { label: "Privacy", slug: "privacy" },
];
