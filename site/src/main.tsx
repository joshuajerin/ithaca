import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider } from "@clerk/react";
import { BrowserRouter } from "react-router-dom";
import { inject } from "@vercel/analytics";
import { injectSpeedInsights } from "@vercel/speed-insights";
import "./index.css";
import App from "./App";

inject();
injectSpeedInsights();

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as
  | string
  | undefined;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      {clerkPublishableKey ? (
        <ClerkProvider publishableKey={clerkPublishableKey}>
          <App authMode="clerk" />
        </ClerkProvider>
      ) : (
        <App authMode="signed-out" />
      )}
    </BrowserRouter>
  </StrictMode>,
);
