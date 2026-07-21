import { SignIn, SignUp } from "@clerk/react";
import { Link, Navigate, useLocation } from "react-router-dom";
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
  const isAgentLink = isAgentLinkLocation(pathname, hash);
  const isSignUp = pathname.startsWith("/sign-up");
  const isAccess = pathname.startsWith("/access");
  const signInUrl = signInUrlFor(pathname, search, hash);
  const redirectAfterSignIn = safeRedirectUrl(search);

  if (isAgentLink) return <Navigate to={signInUrl} replace />;
  if (!isSignUp && !isAccess) return <Navigate to="/sign-up" replace />;

  return (
    <div className="auth">
      <div className="auth-bg" />
      <div className="auth-card clerk-auth-card">
        <div className="auth-brand">
          <IthacaMark size={30} />
          <div>Ithaca</div>
        </div>

        {isSignUp ? (
          <SignUp appearance={embeddedClerkAppearance} path="/sign-up" routing="path" />
        ) : (
          <SignIn
            appearance={embeddedClerkAppearance}
            path="/access"
            routing="path"
            forceRedirectUrl={redirectAfterSignIn}
            fallbackRedirectUrl={redirectAfterSignIn}
          />
        )}

        <div className="auth-mode-row">
          <span>{isSignUp ? "Already have an account?" : "New to Ithaca?"}</span>
          <Link className="link-btn auth-mode-link" data-auth-switch to={isSignUp ? "/access" : "/sign-up"}>
            {isSignUp ? "Sign in" : "Create account"}
          </Link>
        </div>

        <p className="auth-consent">
          By continuing you agree to our{" "}
          <a href={legalUrl("terms")} target="_blank" rel="noopener noreferrer">Terms</a>{" "}
          and{" "}
          <a href={legalUrl("privacy")} target="_blank" rel="noopener noreferrer">Privacy Policy</a>.
        </p>
      </div>
    </div>
  );
}
