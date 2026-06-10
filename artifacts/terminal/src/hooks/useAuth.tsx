import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  signup as signupRequest,
} from "@workspace/api-client-react";
import type {
  AuthIdentity,
  LoginRequest,
  SignupRequest,
} from "@workspace/api-client-react";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AcceptInviteInput {
  token: string;
  name?: string;
  password: string;
}

interface AuthContextValue {
  status: AuthStatus;
  identity: AuthIdentity | null;
  login: (req: LoginRequest) => Promise<void>;
  signup: (req: SignupRequest) => Promise<void>;
  acceptInvite: (req: AcceptInviteInput) => Promise<void>;
  logout: () => Promise<void>;
  // True when the current user's role is allowed to perform `action`. This is a
  // UI convenience only — the server enforces the same matrix authoritatively
  // (it returns 403 regardless of what the UI shows).
  can: (action: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// Holds the authenticated identity for the whole app. On mount it asks the
// backend who the current user is (via the session cookie); a 401 simply means
// "logged out". Login/signup set the identity in place so the gate re-renders
// straight into the terminal without a full reload.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [identity, setIdentity] = useState<AuthIdentity | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getCurrentUser();
        if (!cancelled) {
          setIdentity(me);
          setStatus("authenticated");
        }
      } catch {
        if (!cancelled) {
          setIdentity(null);
          setStatus("anonymous");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (req: LoginRequest) => {
    const me = await loginRequest(req);
    setIdentity(me);
    setStatus("authenticated");
  }, []);

  const signup = useCallback(async (req: SignupRequest) => {
    const me = await signupRequest(req);
    setIdentity(me);
    setStatus("authenticated");
  }, []);

  // Accept a teammate invitation: creates the user inside the inviting firm and
  // starts a session. Not in the generated client, so it posts directly to the
  // public accept-invite endpoint and reuses the same AuthIdentity shape.
  const acceptInvite = useCallback(async (req: AcceptInviteInput) => {
    const res = await fetch("/api/auth/accept-invite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const detail = (data as { detail?: string } | null)?.detail;
      throw new Error(detail || `Request failed (${res.status})`);
    }
    setIdentity(data as AuthIdentity);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      setIdentity(null);
      setStatus("anonymous");
    }
  }, []);

  const can = useCallback(
    (action: string) => !!identity?.permissions?.includes(action),
    [identity],
  );

  return (
    <AuthContext.Provider value={{ status, identity, login, signup, acceptInvite, logout, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
