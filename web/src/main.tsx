import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Analytics } from "@vercel/analytics/react";
import { ClerkProvider } from "@clerk/react";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import "./index.css";

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;
const clerkLocalization = {
  signIn: {
    start: {
      title: "Sign in",
      subtitle: "Welcome back.",
    },
  },
  signUp: {
    start: {
      title: "Create account",
      subtitle: "Get started.",
    },
  },
};

const clerkAppearance = {
  variables: {
    fontFamily: '"Pliant", "Helvetica Neue", Helvetica, ui-sans-serif, system-ui, sans-serif',
    fontFamilyButtons: '"Pliant", "Helvetica Neue", Helvetica, ui-sans-serif, system-ui, sans-serif',
  },
} as const;

function MissingClerkConfig() {
  return (
    <div className="auth">
      <div className="auth-bg" />
      <div className="auth-card auth-callback">
        <div className="auth-brand">
          <div>
            Ithaca
          </div>
        </div>
        <h1 className="auth-title">Authentication is not configured</h1>
        <div className="banner">
          Set <code>VITE_CLERK_PUBLISHABLE_KEY</code> for this environment.
        </div>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {clerkPublishableKey ? (
      <ClerkProvider
        publishableKey={clerkPublishableKey}
        localization={clerkLocalization}
        appearance={clerkAppearance}
        signInUrl="/"
        signUpUrl="/sign-up"
        waitlistUrl="/waitlist"
      >
        <AuthProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
          <Analytics />
        </AuthProvider>
      </ClerkProvider>
    ) : (
      <MissingClerkConfig />
    )}
  </StrictMode>,
);
