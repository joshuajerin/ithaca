import { SignIn, SignUp } from "@clerk/react";
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { DoombergMark } from "../auth/icons";

const embeddedClerkAppearance = {
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
            Doomberg
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
      </div>
    </div>
  );
}
