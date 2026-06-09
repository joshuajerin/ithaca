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

interface AuthContextValue {
  status: AuthStatus;
  identity: AuthIdentity | null;
  login: (req: LoginRequest) => Promise<void>;
  signup: (req: SignupRequest) => Promise<void>;
  logout: () => Promise<void>;
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

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      setIdentity(null);
      setStatus("anonymous");
    }
  }, []);

  return (
    <AuthContext.Provider value={{ status, identity, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
