import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const authPageSource = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "pages", "AuthPage.tsx"),
  "utf8",
);
const agentLinkSource = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "pages", "AgentLink.tsx"),
  "utf8",
);

describe("auth approval entry page", () => {
  it("routes agent approvals through the established sign-in route", () => {
    expect(authPageSource).toContain('pathname.startsWith("/agent-link")');
    expect(authPageSource).toContain('hash.startsWith("#/agent-link")');
    expect(authPageSource).toContain("<Navigate to={signInUrl} replace />");
    expect(authPageSource).toContain('path="/access"');
    expect(authPageSource).toContain("forceRedirectUrl={redirectAfterSignIn}");
    expect(authPageSource).toContain("fallbackRedirectUrl={redirectAfterSignIn}");
    expect(authPageSource).toContain('if (!isAgentLinkLocation(pathname, hash)) return "/access";');
    expect(agentLinkSource).toContain("Create an Ithaca compatibility key");
    expect(agentLinkSource).toContain("Create compatibility key");
  });

  it("offers direct account creation", () => {
    expect(authPageSource).toContain('to={isSignUp ? "/access" : "/sign-up"}');
    expect(authPageSource).toContain('"Create account"');
    expect(authPageSource).toContain('import { SignIn, SignUp } from "@clerk/react";');
  });
});
