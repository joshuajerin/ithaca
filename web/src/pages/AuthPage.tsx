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
  const { pathname, search, hash } = useLocation();
  const isSignUp = pathname.startsWith("/sign-up");
  const isWaitlist = pathname.startsWith("/waitlist");
  const isAgentLink = pathname.startsWith("/agent-link");
  const redirectUrl = `${pathname}${search}${hash}`;

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
        ) : isAgentLink ? (
          <>
            <header>
              <h1 className="auth-title">Sign in to approve the agent</h1>
              <p className="auth-sub">
                Once you’re signed in, you’ll return here to approve Doomberg MCP access.
              </p>
            </header>
            <SignIn
              appearance={embeddedClerkAppearance}
              path="/agent-link"
              routing="path"
              forceRedirectUrl={redirectUrl}
              fallbackRedirectUrl={redirectUrl}
              withSignUp={false}
            />
          </>
        ) : isSignUp ? (
          <SignUp appearance={embeddedClerkAppearance} path="/sign-up" routing="path" />
        ) : (
          <SignIn appearance={embeddedClerkAppearance} path="/" routing="path" />
        )}

        {!isAgentLink && (
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
    </div>
  );
}
