import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@workspace/api-client-react";

type Mode = "login" | "signup";

function messageFromError(err: unknown): string {
  if (err instanceof ApiError) {
    const data = err.data as { detail?: string } | undefined;
    if (data?.detail) return data.detail;
  }
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong. Please try again.";
}

// Pull a one-time invite token out of the URL (?invite=…). When present, the
// gate shows the accept-invite screen instead of the login/register toggle.
function inviteTokenFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const t = new URLSearchParams(window.location.search).get("invite");
    return t && t.trim() ? t.trim() : null;
  } catch {
    return null;
  }
}

interface InvitePreview {
  email: string;
  name: string | null;
  role: string;
  firmName: string;
}

// The logged-out gate: a single editorial panel that toggles between signing in
// to an existing firm and registering a new firm (whose first user becomes the
// admin). On success the AuthProvider flips to authenticated and the terminal
// renders in place.
export function AuthScreen() {
  const inviteToken = inviteTokenFromUrl();
  if (inviteToken) return <AcceptInviteScreen token={inviteToken} />;
  return <LoginScreen />;
}

function LoginScreen() {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [firmName, setFirmName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isSignup = mode === "signup";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      if (isSignup) {
        await signup({ firmName, name, email, password });
      } else {
        await login({ email, password });
      }
    } catch (err) {
      setError(messageFromError(err));
      setBusy(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  return (
    <div className="min-h-screen w-full bg-black text-white flex items-center justify-center px-5 py-10">
      <div className="w-full max-w-md">
        <div className="mb-10 flex flex-col items-center text-center">
          <span className="font-serif text-3xl leading-none tracking-tight">
            Agentic&nbsp;Terminal
          </span>
          <span className="editorial-label text-[9px] text-muted-foreground mt-2">
            Synthetic Market Intelligence
          </span>
        </div>

        <div className="border border-border bg-black/60 backdrop-blur-sm p-7">
          <div className="flex items-center gap-6 mb-7">
            <button
              type="button"
              onClick={() => switchMode("login")}
              className={`editorial-label text-[10px] pb-1.5 border-b transition-colors ${
                !isSignup
                  ? "text-white border-white"
                  : "text-muted-foreground border-transparent hover:text-white"
              }`}
            >
              Sign in
            </button>
            <button
              type="button"
              onClick={() => switchMode("signup")}
              className={`editorial-label text-[10px] pb-1.5 border-b transition-colors ${
                isSignup
                  ? "text-white border-white"
                  : "text-muted-foreground border-transparent hover:text-white"
              }`}
            >
              Register a firm
            </button>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {isSignup && (
              <Field
                label="Firm name"
                value={firmName}
                onChange={setFirmName}
                placeholder="Acme Capital"
                autoFocus
              />
            )}
            {isSignup && (
              <Field
                label="Your name"
                value={name}
                onChange={setName}
                placeholder="Jane Trader"
              />
            )}
            <Field
              label="Email"
              type="email"
              value={email}
              onChange={setEmail}
              placeholder="you@firm.com"
              autoFocus={!isSignup}
            />
            <Field
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              placeholder={isSignup ? "At least 8 characters" : "••••••••"}
            />

            {error && (
              <p className="text-[11px] leading-snug text-red-400 border border-red-500/30 bg-red-500/10 px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="mt-2 flex items-center justify-center gap-2 px-4 py-3 bg-white text-black editorial-label text-[10px] hover:bg-gray-200 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {busy ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} />
              ) : (
                <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />
              )}
              {isSignup ? "Create firm & admin" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-[10px] text-muted-foreground leading-relaxed">
          {isSignup ? (
            <>
              Registering creates a new firm with you as its first administrator.
            </>
          ) : (
            <>
              New firm?{" "}
              <button
                type="button"
                onClick={() => switchMode("signup")}
                className="text-white underline underline-offset-2 hover:text-gray-300"
              >
                Register here
              </button>
              .
            </>
          )}
        </p>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  autoFocus,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="editorial-label text-[9px] text-muted-foreground">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete={
          type === "password"
            ? "current-password"
            : type === "email"
            ? "email"
            : "off"
        }
        className="bg-black border border-border px-3 py-2.5 font-serif text-sm text-white placeholder:text-muted-foreground/50 focus:outline-none focus:border-white transition-colors"
      />
    </label>
  );
}

// Shown when the user arrives via an invite link (?invite=<token>). It previews
// the invitation (firm, email, role) then lets them set a name + password to
// join the inviting firm. On success the AuthProvider flips to authenticated.
function AcceptInviteScreen({ token }: { token: string }) {
  const { acceptInvite } = useAuth();
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/auth/invitation?token=${encodeURIComponent(token)}`);
        const data = await res.json().catch(() => null);
        if (!res.ok) {
          const detail = (data as { detail?: string } | null)?.detail;
          throw new Error(detail || "This invitation is no longer valid.");
        }
        if (!cancelled) {
          setPreview(data as InvitePreview);
          setName((data as InvitePreview).name || "");
        }
      } catch (err) {
        if (!cancelled) setInvalid(messageFromError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      await acceptInvite({ token, name: name.trim() || undefined, password });
      // Clean the invite token out of the URL after joining.
      try {
        window.history.replaceState(null, "", window.location.pathname);
      } catch {
        /* non-fatal */
      }
    } catch (err) {
      setError(messageFromError(err));
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen w-full bg-black text-white flex items-center justify-center px-5 py-10">
      <div className="w-full max-w-md">
        <div className="mb-10 flex flex-col items-center text-center">
          <span className="font-serif text-3xl leading-none tracking-tight">Agentic&nbsp;Terminal</span>
          <span className="editorial-label text-[9px] text-muted-foreground mt-2">Synthetic Market Intelligence</span>
        </div>

        <div className="border border-border bg-black/60 backdrop-blur-sm p-7">
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground py-4">
              <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} />
              <span className="text-xs font-serif">Checking your invitation…</span>
            </div>
          ) : invalid ? (
            <div className="flex flex-col gap-3">
              <span className="font-serif text-lg">Invitation unavailable</span>
              <p className="text-[11px] leading-snug text-red-400 border border-red-500/30 bg-red-500/10 px-3 py-2">
                {invalid}
              </p>
              <a href={window.location.pathname} className="text-white underline underline-offset-2 text-[10px] hover:text-gray-300">
                Go to sign in
              </a>
            </div>
          ) : preview ? (
            <>
              <div className="mb-6 flex flex-col gap-1">
                <span className="editorial-label text-[9px] text-muted-foreground">You've been invited to</span>
                <span className="font-serif text-xl leading-none">{preview.firmName}</span>
                <span className="editorial-label text-[9px] text-muted-foreground mt-1.5 capitalize">
                  {preview.email} · {preview.role}
                </span>
              </div>
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <Field label="Your name" value={name} onChange={setName} placeholder="Jane Trader" autoFocus />
                <Field
                  label="Set a password"
                  type="password"
                  value={password}
                  onChange={setPassword}
                  placeholder="At least 8 characters"
                />
                {error && (
                  <p className="text-[11px] leading-snug text-red-400 border border-red-500/30 bg-red-500/10 px-3 py-2">
                    {error}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={busy}
                  className="mt-2 flex items-center justify-center gap-2 px-4 py-3 bg-white text-black editorial-label text-[10px] hover:bg-gray-200 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={2} /> : <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />}
                  Join {preview.firmName}
                </button>
              </form>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
