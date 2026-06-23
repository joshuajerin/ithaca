import { useAuth as useCurrentAuth } from "../auth/AuthContext";

export function useAuth() {
  const auth = useCurrentAuth();

  return {
    ...auth,
    can: (_permission: string) => true,
  };
}
