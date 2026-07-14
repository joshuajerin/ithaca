import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const authPageSource = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "pages", "AuthPage.tsx"),
  "utf8",
);

describe("auth approval entry page", () => {
  it("keeps the agent-link route on a sign-in-then-approve flow", () => {
    expect(authPageSource).toContain('pathname.startsWith("/agent-link")');
    expect(authPageSource).toContain('path="/agent-link"');
    expect(authPageSource).toContain("forceRedirectUrl={redirectUrl}");
    expect(authPageSource).toContain("fallbackRedirectUrl={redirectUrl}");
    expect(authPageSource).toContain("withSignUp={false}");
    expect(authPageSource).toContain("Sign in to approve the agent");
  });
});
