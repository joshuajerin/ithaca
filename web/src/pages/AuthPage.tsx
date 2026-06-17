import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { beginOAuth, providerConfigured, type Provider } from "../auth/oauth";
import { DoombergMark, GoogleIcon, GithubIcon } from "../auth/icons";

// The sign-in / create-account gate. Renders before the dashboard whenever
// there is no session. Google + GitHub start the OAuth redirect when configured,
// otherwise fall back to a labelled demo session so the flow is testable.
export function AuthPage() {
  const { signInDemo } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [busy, setBusy] = useState<Provider | null>(null);

  function onProvider(p: Provider) {
    if (providerConfigured(p)) {
      setBusy(p);
      beginOAuth(p, mode);
    } else {
      // No client id configured → demo sign-in so the app is usable now.
      signInDemo(p);
    }
  }

  const anyConfigured = providerConfigured("google") || providerConfigured("github");

  return (
    <div className="auth">
      <div className="auth-bg" />
      <div className="auth-card">
        <div className="auth-brand">
          <DoombergMark size={30} />
          <div>
            Doomberg
            <small>Terminal</small>
          </div>
        </div>

        <h1 className="auth-title">
          {mode === "signin" ? "Sign in to the terminal" : "Create your account"}
        </h1>
        <p className="auth-sub">
          {mode === "signin"
            ? "Watch your agent research, deploy, and trade — in the glass box."
            : "Spin up a tenant and point your agent at Doomberg over MCP."}
        </p>

        <div className="auth-providers">
          <button
            className="oauth-btn"
            onClick={() => onProvider("google")}
            disabled={busy !== null}
          >
            <GoogleIcon />
            <span>{mode === "signin" ? "Continue with Google" : "Sign up with Google"}</span>
            {busy === "google" && <span className="oauth-spin">…</span>}
          </button>
          <button
            className="oauth-btn"
            onClick={() => onProvider("github")}
            disabled={busy !== null}
          >
            <GithubIcon />
            <span>{mode === "signin" ? "Continue with GitHub" : "Sign up with GitHub"}</span>
            {busy === "github" && <span className="oauth-spin">…</span>}
          </button>
        </div>

        {!anyConfigured && (
          <div className="auth-note">
            OAuth client ids not set — buttons use a <strong>demo session</strong>.
            Add <code>VITE_GOOGLE_CLIENT_ID</code> / <code>VITE_GITHUB_CLIENT_ID</code>{" "}
            and a backend exchange to enable real sign-in.
          </div>
        )}

        <div className="auth-divider"><span>or</span></div>

        <button className="btn auth-demo" onClick={() => signInDemo("demo")}>
          Continue in demo mode
        </button>

        <div className="auth-switch">
          {mode === "signin" ? (
            <>
              New to Doomberg?{" "}
              <button className="link-btn" onClick={() => setMode("signup")}>
                Create an account
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button className="link-btn" onClick={() => setMode("signin")}>
                Sign in
              </button>
            </>
          )}
        </div>
      </div>

      <div className="auth-foot">
        Never runs your agent · Never executes agent-authored code
      </div>
    </div>
  );
}
