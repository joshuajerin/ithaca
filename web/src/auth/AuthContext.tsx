import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Provider, SessionUser } from "./oauth";

// ---------------------------------------------------------------------------
// Session + connected-integrations state, persisted to localStorage so a
// signed-in user survives reloads. The backend session token (when a real
// exchange runs) is what api.ts would attach; here we keep the user profile.
// ---------------------------------------------------------------------------

const SESSION_KEY = "doomberg.session";
const INTEGRATIONS_KEY = "doomberg.integrations";

export type Integrations = Record<Provider, boolean>;

interface AuthState {
  user: SessionUser | null;
  integrations: Integrations;
  signInDemo: (provider?: SessionUser["provider"]) => void;
  setSession: (u: SessionUser) => void;
  signOut: () => void;
  setIntegration: (p: Provider, connected: boolean) => void;
}

const Ctx = createContext<AuthState | null>(null);

function loadSession(): SessionUser | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  } catch {
    return null;
  }
}

function loadIntegrations(): Integrations {
  try {
    const raw = localStorage.getItem(INTEGRATIONS_KEY);
    if (raw) return { google: false, github: false, ...(JSON.parse(raw) as Partial<Integrations>) };
  } catch {
    /* ignore */
  }
  return { google: false, github: false };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(loadSession);
  const [integrations, setIntegrations] = useState<Integrations>(loadIntegrations);

  const setSession = useCallback((u: SessionUser) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(u));
    setUser(u);
    if (u.provider === "google" || u.provider === "github") {
      setIntegrations((prev) => {
        const next = { ...prev, [u.provider as Provider]: true };
        localStorage.setItem(INTEGRATIONS_KEY, JSON.stringify(next));
        return next;
      });
    }
  }, []);

  const signInDemo = useCallback(
    (provider: SessionUser["provider"] = "demo") => {
      const names: Record<string, string> = {
        github: "Octo Demo",
        google: "Ada Demo",
        demo: "Demo Operator",
      };
      setSession({
        id: `demo-${Math.random().toString(36).slice(2, 8)}`,
        name: names[provider] ?? "Demo Operator",
        email: "operator@demo.doomberg.dev",
        provider,
      });
    },
    [setSession],
  );

  const signOut = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    setUser(null);
  }, []);

  const setIntegration = useCallback((p: Provider, connected: boolean) => {
    setIntegrations((prev) => {
      const next = { ...prev, [p]: connected };
      localStorage.setItem(INTEGRATIONS_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, integrations, signInDemo, setSession, signOut, setIntegration }),
    [user, integrations, signInDemo, setSession, signOut, setIntegration],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be used within <AuthProvider>");
  return c;
}
