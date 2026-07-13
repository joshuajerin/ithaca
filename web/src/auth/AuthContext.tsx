import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";
import { useAuth as useClerkAuth, useClerk, useUser } from "@clerk/react";
import { setAuthTokenProvider } from "../api";
import { USE_CLERK_API_AUTH } from "../config";

export type Provider = "google" | "github";

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  avatarUrl?: string;
  provider: "doomberg";
}

export type Integrations = Record<Provider, boolean>;

interface AuthState {
  user: SessionUser | null;
  token: string | null;
  integrations: Integrations;
  signOut: () => void;
  manageAccount: () => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { getToken, signOut: clerkSignOut } = useClerkAuth();
  const { user: clerkUser } = useUser();
  const clerk = useClerk();

  useEffect(() => {
    if (!USE_CLERK_API_AUTH) {
      setAuthTokenProvider(null);
      return () => setAuthTokenProvider(null);
    }
    setAuthTokenProvider(async () => (await getToken()) ?? null);
    return () => setAuthTokenProvider(null);
  }, [getToken]);

  const user = useMemo<SessionUser | null>(() => {
    if (!clerkUser) return null;
    const email = clerkUser.primaryEmailAddress?.emailAddress ?? "";
    return {
      id: clerkUser.id,
      name: clerkUser.fullName || clerkUser.username || email || "Doomberg user",
      email,
      avatarUrl: clerkUser.imageUrl || undefined,
      provider: "doomberg",
    };
  }, [clerkUser]);

  const integrations = useMemo<Integrations>(() => {
    const providers = new Set(
      (clerkUser?.externalAccounts ?? []).map((account) => String(account.provider).toLowerCase()),
    );
    return {
      google: providers.has("google") || providers.has("oauth_google"),
      github: providers.has("github") || providers.has("oauth_github"),
    };
  }, [clerkUser]);

  const signOut = useCallback(() => {
    void clerkSignOut();
  }, [clerkSignOut]);

  const manageAccount = useCallback(() => {
    clerk.openUserProfile();
  }, [clerk]);

  const value = useMemo<AuthState>(
    () => ({ user, token: null, integrations, signOut, manageAccount }),
    [user, integrations, signOut, manageAccount],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be used within <AuthProvider>");
  return c;
}
