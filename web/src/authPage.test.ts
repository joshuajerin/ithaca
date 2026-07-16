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
  it("keeps the waitlist first and exposes the approved-user sign-in route", () => {
    expect(authPageSource).toContain('pathname.startsWith("/agent-link")');
    expect(authPageSource).toContain("If approved,");
    expect(authPageSource).toContain('hash.startsWith("#/agent-link")');
    expect(authPageSource).toContain('to={signInUrl}');
    expect(authPageSource).toContain('signInUrl={signInUrl}');
    expect(authPageSource).toContain('path="/access"');
    expect(authPageSource).toContain("forceRedirectUrl={redirectAfterSignIn}");
    expect(authPageSource).toContain("fallbackRedirectUrl={redirectAfterSignIn}");
    expect(agentLinkSource).toContain("Create an Ithaca compatibility key");
    expect(agentLinkSource).toContain("Create compatibility key");
  });
});
