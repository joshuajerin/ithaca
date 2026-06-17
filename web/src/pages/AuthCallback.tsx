import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { exchangeCode, type Provider } from "../auth/oauth";
import { DoombergMark } from "../auth/icons";

// Rendered (outside the HashRouter) by main.tsx when the browser lands on the
// OAuth redirect path. Verifies CSRF state, exchanges the code via the backend,
// stores the session, then returns to the dashboard.
export function AuthCallback() {
  const { setSession } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const returnedState = params.get("state");
    const oauthError = params.get("error");
    const provider = sessionStorage.getItem("oauth_provider") as Provider | null;
    const expectedState = sessionStorage.getItem("oauth_state");

    function backToAuth() {
      window.location.replace("/");
    }

    if (oauthError) {
      setError(`Provider returned: ${oauthError}`);
      return;
    }
    if (!code || !provider) {
      setError("Missing authorization code.");
      return;
    }
    if (!returnedState || returnedState !== expectedState) {
      setError("State mismatch — possible CSRF. Aborted.");
      return;
    }

    sessionStorage.removeItem("oauth_state");

    exchangeCode(provider, code)
      .then((user) => {
        setSession(user);
        backToAuth();
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Token exchange failed.");
      });
  }, [setSession]);

  return (
    <div className="auth">
      <div className="auth-bg" />
      <div className="auth-card auth-callback">
        <div className="auth-brand">
          <DoombergMark size={30} />
          <div>
            Doomberg
            <small>Terminal</small>
          </div>
        </div>
        {error ? (
          <>
            <h1 className="auth-title">Sign-in failed</h1>
            <div className="banner">{error}</div>
            <a className="btn" href="/">
              Back to sign in
            </a>
          </>
        ) : (
          <>
            <h1 className="auth-title">Completing sign-in…</h1>
            <p className="auth-sub">Exchanging your authorization with the provider.</p>
          </>
        )}
      </div>
    </div>
  );
}
