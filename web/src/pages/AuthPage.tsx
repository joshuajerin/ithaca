import { SignIn, SignUp } from "@clerk/react";
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
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
  const [isSignUp, setIsSignUp] = useState(pathname === "/sign-up");

  useEffect(() => {
    setIsSignUp(pathname === "/sign-up");
  }, [pathname]);

  return (
    <div className="auth">
      <div className="auth-bg" />
      <div className="auth-card clerk-auth-card">
        <div className="auth-brand">
          <DoombergMark size={30} />
          <div>
            Ithaca
          </div>
        </div>

        {isSignUp ? (
          <SignUp appearance={embeddedClerkAppearance} path="/" routing="path" />
        ) : (
          <SignIn appearance={embeddedClerkAppearance} path="/" routing="path" />
        )}

        <div className="auth-mode-row">
          <span>{isSignUp ? "Already have an account?" : "Don't have an account?"}</span>
          <button
            className="link-btn auth-mode-link"
            data-auth-switch
            type="button"
            onClick={() => setIsSignUp((current) => !current)}
          >
            {isSignUp ? "Sign in" : "Sign up"}
          </button>
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
