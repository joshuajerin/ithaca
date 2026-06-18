import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { Analytics } from "@vercel/analytics/react";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { AuthCallback } from "./pages/AuthCallback";
import "./index.css";

// OAuth providers redirect to a real path (/auth/callback), not a hash route.
// Intercept it here, before the HashRouter mounts, to run the code exchange.
const isCallback = window.location.pathname.replace(/\/+$/, "") === "/auth/callback";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      {isCallback ? (
        <AuthCallback />
      ) : (
        <HashRouter>
          <App />
        </HashRouter>
      )}
      <Analytics />
    </AuthProvider>
  </StrictMode>,
);
