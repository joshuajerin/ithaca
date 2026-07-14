import { describe, expect, it } from "vitest";
import { shouldShowWaitlist } from "./AuthPage";

describe("shouldShowWaitlist", () => {
  it("renders the waitlist for public routes", () => {
    expect(shouldShowWaitlist("/")).toBe(true);
    expect(shouldShowWaitlist("/waitlist")).toBe(true);
  });

  it("reserves the access route for existing approved users", () => {
    expect(shouldShowWaitlist("/access")).toBe(false);
  });
});
