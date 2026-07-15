import { describe, expect, it } from "vitest";
import { safeRedirectUrl, shouldShowWaitlist, signInUrlFor } from "./AuthPage";

describe("shouldShowWaitlist", () => {
  it("renders the waitlist for public routes", () => {
    expect(shouldShowWaitlist("/")).toBe(true);
    expect(shouldShowWaitlist("/waitlist")).toBe(true);
    expect(shouldShowWaitlist("/agent-link")).toBe(true);
  });

  it("reserves the access route for existing approved users", () => {
    expect(shouldShowWaitlist("/access")).toBe(false);
  });

  it("returns an approved agent user to their pending approval link", () => {
    expect(signInUrlFor("/agent-link", "?token=abc", "#approve")).toBe(
      "/access?redirect_url=%2Fagent-link%3Ftoken%3Dabc%23approve",
    );
    expect(safeRedirectUrl("?redirect_url=%2Fagent-link%3Ftoken%3Dabc%23approve")).toBe(
      "/agent-link?token=abc#approve",
    );
  });

  it("does not permit an external post-sign-in redirect", () => {
    expect(safeRedirectUrl("?redirect_url=https%3A%2F%2Fevil.example")).toBe("/dashboard");
    expect(safeRedirectUrl("?redirect_url=%2F%2Fevil.example")).toBe("/dashboard");
  });
});
