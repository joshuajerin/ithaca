
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
  const { pathname } = useLocation();
  const isWaitlist = shouldShowWaitlist(pathname);

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
