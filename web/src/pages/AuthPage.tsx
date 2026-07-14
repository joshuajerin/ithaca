
import { SignIn, Waitlist } from "@clerk/react";
import { useLocation } from "react-router-dom";
import { IthacaMark } from "../auth/icons";
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

export function shouldShowWaitlist(pathname: string) {
  return !pathname.startsWith("/access");
}

export function AuthPage() {
  const { pathname, search, hash } = useLocation();
  const isAgentLink = pathname.startsWith("/agent-link");
  const isWaitlist = !isAgentLink && shouldShowWaitlist(pathname);
  const redirectUrl = `${pathname}${search}${hash}`;

  return (
    <div className="auth">
      <div className="auth-bg" />
      <div className="auth-card clerk-auth-card">
        <div className="auth-brand">
          <IthacaMark size={30} />
          <div>
            Ithaca
          </div>
        </div>

        {isWaitlist ? (
          <Waitlist appearance={embeddedClerkAppearance} signInUrl="/access" />
        ) : isAgentLink ? (
          <>
            <header>
              <h1 className="auth-title">Sign in to approve the agent</h1>
              <p className="auth-sub">
                Once you’re signed in, you’ll return here to approve Ithaca MCP access.
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
        ) : (
          <SignIn appearance={embeddedClerkAppearance} path="/access" routing="path" />
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
