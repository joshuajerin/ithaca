// Where the marketing site sends users to sign in / launch the product.
// Points at the dashboard app (the Ithaca terminal). Override with VITE_APP_URL.
export const APP_URL: string =
  (import.meta.env.VITE_APP_URL as string | undefined) ?? "http://localhost:5173/";

export const DOCS_URL: string =
  (import.meta.env.VITE_DOCS_URL as string | undefined) ?? "https://docs.tradeithaca.com/";

export const TERMS_URL: string =
  (import.meta.env.VITE_TERMS_URL as string | undefined) ?? DOCS_URL;

export const PRIVACY_URL: string =
  (import.meta.env.VITE_PRIVACY_URL as string | undefined) ?? DOCS_URL;

export const INSTALL_COMMAND = "curl -fsSL https://app.tradeithaca.com/install.py | python3";
