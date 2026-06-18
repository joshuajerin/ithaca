// Where the marketing site sends users to sign in / launch the product.
// Points at the dashboard app (the Doomberg terminal). Override with VITE_APP_URL.
export const APP_URL: string =
  (import.meta.env.VITE_APP_URL as string | undefined) ?? "http://localhost:5173/";
