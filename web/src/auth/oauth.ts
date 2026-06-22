import { API_BASE } from "../config";

// ---------------------------------------------------------------------------
// OAuth (Google + GitHub), authorization-code flow.
//
// The browser starts the redirect; the SECRET-bearing token exchange happens on
// the backend (rest-gateway), so no client secret ever ships to the browser.
// If a provider's client id is not configured (VITE_*_CLIENT_ID), the UI falls
// back to a local demo sign-in so the whole flow is testable without creds.
//
// Backend contract the exchange expects (implement in rest-gateway):
//   POST {API_BASE}/auth/{provider}/exchange  { code, redirect_uri }
//     -> 200 { user: { id, name, email, avatarUrl?, provider } }
// ---------------------------------------------------------------------------

export type Provider = "google" | "github";

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  avatarUrl?: string;
  provider: Provider | "demo" | "email";
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
const GITHUB_CLIENT_ID = import.meta.env.VITE_GITHUB_CLIENT_ID as string | undefined;

// OAuth requires a path (not a hash) redirect URI. main.tsx intercepts this path
// before the HashRouter mounts and runs the exchange.
export const REDIRECT_URI: string =
  (import.meta.env.VITE_OAUTH_REDIRECT as string | undefined) ||
  `${window.location.origin}/auth/callback`;

export function providerConfigured(p: Provider): boolean {
  return p === "google" ? Boolean(GOOGLE_CLIENT_ID) : Boolean(GITHUB_CLIENT_ID);
}

function randomState(): string {
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

// Kick off the provider's authorization redirect. We stash the CSRF state and
// the chosen provider/intent so the callback can verify + resume.
export function beginOAuth(provider: Provider, intent: "signin" | "signup" | "link" = "signin"): void {
  const state = randomState();
  sessionStorage.setItem("oauth_state", state);
  sessionStorage.setItem("oauth_provider", provider);
  sessionStorage.setItem("oauth_intent", intent);

  let url: string;
  if (provider === "google") {
    const params = new URLSearchParams({
      client_id: GOOGLE_CLIENT_ID ?? "",
      redirect_uri: REDIRECT_URI,
      response_type: "code",
      scope: "openid email profile",
      state,
      access_type: "offline",
      include_granted_scopes: "true",
      prompt: "select_account",
    });
    url = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  } else {
    const params = new URLSearchParams({
      client_id: GITHUB_CLIENT_ID ?? "",
      redirect_uri: REDIRECT_URI,
      scope: "read:user user:email",
      state,
      allow_signup: "true",
    });
    url = `https://github.com/login/oauth/authorize?${params.toString()}`;
  }
  window.location.assign(url);
}

// Exchange the returned auth code for a session via the backend.
export async function exchangeCode(
  provider: Provider,
  code: string,
): Promise<{ user: SessionUser; token: string }> {
  const res = await fetch(`${API_BASE}/auth/${provider}/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, redirect_uri: REDIRECT_URI }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Token exchange failed (${res.status})${body ? `: ${body}` : ""}`);
  }
  const data = (await res.json()) as { user: SessionUser; token: string };
  return { user: data.user, token: data.token };
}
