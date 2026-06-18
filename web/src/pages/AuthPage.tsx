import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { beginOAuth, providerConfigured, type Provider, type SessionUser } from "../auth/oauth";
import { DoombergMark, GoogleIcon, GithubIcon } from "../auth/icons";
import { api } from "../api";

export function AuthPage() {
  const { signInDemo, setSession } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [busy, setBusy] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  function onProvider(p: Provider) {
    if (providerConfigured(p)) {
      setBusy(p);
      beginOAuth(p, mode);
    } else {
      signInDemo(p);
    }
  }

  async function onEmailSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy("email");
    try {
      const result = mode === "signup"
        ? await api.signUp(email, name, password)
        : await api.signIn(email, password);
      const u = result.user as Record<string, unknown>;
      setSession(
        {
          id: String(u.id ?? ""),
          name: String(u.name ?? email),
          email: String(u.email ?? email),
          avatarUrl: u.avatarUrl ? String(u.avatarUrl) : undefined,
          provider: "email",
        } as SessionUser,
        result.token,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(null);
    }
  }

  const anyOAuthConfigured = providerConfigured("google") || providerConfigured("github");

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

        {/* OAuth buttons */}
        <div className="auth-providers">
          <button className="oauth-btn" onClick={() => onProvider("google")} disabled={busy !== null}>
            <GoogleIcon />
            <span>{mode === "signin" ? "Continue with Google" : "Sign up with Google"}</span>
            {busy === "google" && <span className="oauth-spin">…</span>}
          </button>
          <button className="oauth-btn" onClick={() => onProvider("github")} disabled={busy !== null}>
            <GithubIcon />
            <span>{mode === "signin" ? "Continue with GitHub" : "Sign up with GitHub"}</span>
            {busy === "github" && <span className="oauth-spin">…</span>}
          </button>
        </div>

        {!anyOAuthConfigured && (
          <div className="auth-note">
            OAuth client ids not configured — buttons use a <strong>demo session</strong>.
            Set <code>VITE_GOOGLE_CLIENT_ID</code> / <code>VITE_GITHUB_CLIENT_ID</code> to enable real OAuth.
          </div>
        )}

        <div className="auth-divider"><span>or</span></div>

        {/* Email + password form */}
        <form className="auth-form" onSubmit={onEmailSubmit}>
          {mode === "signup" && (
            <input
              className="auth-input"
              type="text"
              placeholder="Full name"
              value={name}
              onChange={e => setName(e.target.value)}
              required
              autoComplete="name"
            />
          )}
          <input
            className="auth-input"
            type="email"
            placeholder="Email address"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          <input
            className="auth-input"
            type="password"
            placeholder="Password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
          />
          {error && <div className="auth-error">{error}</div>}
          <button className="btn primary auth-submit" type="submit" disabled={busy !== null}>
            {busy === "email"
              ? (mode === "signup" ? "Creating account…" : "Signing in…")
              : (mode === "signup" ? "Create account" : "Sign in")}
          </button>
        </form>

        <div className="auth-divider"><span>or</span></div>

        <button className="btn auth-demo" onClick={() => signInDemo("demo")}>
          Continue in demo mode
        </button>

        <div className="auth-switch">
          {mode === "signin" ? (
            <>New to Doomberg?{" "}
              <button className="link-btn" onClick={() => { setMode("signup"); setError(null); }}>
                Create an account
              </button>
            </>
          ) : (
            <>Already have an account?{" "}
              <button className="link-btn" onClick={() => { setMode("signin"); setError(null); }}>
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
