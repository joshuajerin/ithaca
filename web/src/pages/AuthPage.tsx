import { SignIn, SignUp } from "@clerk/react";
import { useState } from "react";
import { DoombergMark } from "../auth/icons";
import { legalUrl } from "../lib/legal";

export function AuthPage() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");

  return (
    <div className="auth">
      <div className="auth-bg" />
      <div className="auth-card clerk-auth-card">
        <div className="auth-brand">
          <DoombergMark size={30} />
          <div>
            Doomberg
            <small>Terminal</small>
          </div>
        </div>

        <div className="auth-switch clerk-auth-switch">
          <button
            className={`link-btn ${mode === "signin" ? "active" : ""}`}
            onClick={() => setMode("signin")}
          >
            Sign in
          </button>
          <button
            className={`link-btn ${mode === "signup" ? "active" : ""}`}
            onClick={() => setMode("signup")}
          >
            Create account
          </button>
        </div>

        {mode === "signin" ? (
          <SignIn routing="hash" signUpUrl="#/sign-up" />
        ) : (
          <SignUp routing="hash" signInUrl="#/sign-in" />
        )}

        <p className="auth-consent">
          By continuing you agree to our{" "}
          <a href={legalUrl("terms")} target="_blank" rel="noopener noreferrer">
            Terms
          </a>{" "}
          and{" "}
          <a href={legalUrl("privacy")} target="_blank" rel="noopener noreferrer">
            Privacy Policy
          </a>
          .
        </p>
      </div>

      <div className="auth-foot">
        Never runs your agent · Never executes agent-authored code
      </div>
    </div>
  );
}
