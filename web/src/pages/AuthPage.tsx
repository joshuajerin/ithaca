import { SignIn, SignUp, Waitlist } from "@clerk/react";
import { Link, useLocation } from "react-router-dom";
import { DoombergMark } from "../auth/icons";
import { legalUrl } from "../lib/legal";

const embeddedClerkAppearance = {
  variables: {
    fontFamily: '"Pliant", "Helvetica Neue", Helvetica, ui-sans-serif, system-ui, sans-serif',
    fontFamilyButtons: '"Pliant", "Helvetica Neue", Helvetica, ui-sans-serif, system-ui, sans-serif',
  },
  elements: {
    footerAction: {
      display: "none",
    },
  },
} as const;

export function AuthPage() {
  const { pathname } = useLocation();
  const isSignUp = pathname.startsWith("/sign-up");
  const isWaitlist = pathname.startsWith("/waitlist");

  return (
    <div className="auth">
      <div className="auth-bg" />
      <div className="auth-card clerk-auth-card">
        <div className="auth-brand">
          <DoombergMark size={30} />
          <div>
            Doomberg
          </div>
        </div>

        {isWaitlist ? (
          <Waitlist appearance={embeddedClerkAppearance} />
        ) : isSignUp ? (
          <SignUp appearance={embeddedClerkAppearance} path="/sign-up" routing="path" />
        ) : (
          <SignIn appearance={embeddedClerkAppearance} path="/" routing="path" />
        )}

        <div className="auth-mode-row">
          <span>
            {isWaitlist || isSignUp ? "Already approved?" : "New to Doomberg?"}
          </span>
          <Link
            className="link-btn auth-mode-link"
            data-auth-switch
            to={isWaitlist || isSignUp ? "/" : "/waitlist"}
          >
            {isWaitlist || isSignUp ? "Sign in" : "Join the waitlist"}
          </Link>
        </div>

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
    </div>
  );
}
