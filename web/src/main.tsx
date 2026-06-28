import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { Analytics } from "@vercel/analytics/react";
import { ClerkProvider } from "@clerk/react";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import "./index.css";

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;

function MissingClerkConfig() {
  return (
    <div className="auth">
      <div className="auth-bg" />
      <div className="auth-card auth-callback">
        <div className="auth-brand">
          <div>
            Doomberg
            <small>Terminal</small>
          </div>
        </div>
        <h1 className="auth-title">Clerk is not configured</h1>
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
      <ClerkProvider publishableKey={clerkPublishableKey}>
        <AuthProvider>
        <HashRouter>
          <App />
        </HashRouter>
        <Analytics />
        </AuthProvider>
      </ClerkProvider>
    ) : (
      <MissingClerkConfig />
    )}
  </StrictMode>,
);
