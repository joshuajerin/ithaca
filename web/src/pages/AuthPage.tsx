
import { SignIn, Waitlist } from "@clerk/react";
import { Link, useLocation } from "react-router-dom";
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

export function isAgentLinkLocation(pathname: string, hash = "") {
  return pathname.startsWith("/agent-link") || hash.startsWith("#/agent-link");
}

export function signInUrlFor(pathname: string, search = "", hash = "") {
  if (!isAgentLinkLocation(pathname, hash)) return "/access";

  return `/access?redirect_url=${encodeURIComponent(`${pathname}${search}${hash}`)}`;
}

export function safeRedirectUrl(search: string) {
  const redirectUrl = new URLSearchParams(search).get("redirect_url");

  return redirectUrl?.startsWith("/") && !redirectUrl.startsWith("//")
    ? redirectUrl
    : "/dashboard";
}

export function AuthPage() {
  const { pathname, search, hash } = useLocation();
  const isWaitlist = shouldShowWaitlist(pathname);
  const signInUrl = signInUrlFor(pathname, search, hash);
  const redirectAfterSignIn = safeRedirectUrl(search);

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
          <>
            <Waitlist appearance={embeddedClerkAppearance} signInUrl={signInUrl} />
            <p className="auth-mode-row">
              If approved, <Link className="auth-mode-link" to={signInUrl}>sign in</Link>
            </p>
          </>
        ) : (
          <>
            <SignIn
              appearance={embeddedClerkAppearance}
              path="/access"
              routing="path"
              forceRedirectUrl={redirectAfterSignIn}
              fallbackRedirectUrl={redirectAfterSignIn}
            />
            <p className="auth-mode-row">
              Agent approvals stay connected for at least 30 days unless revoked.
            </p>
          </>
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
