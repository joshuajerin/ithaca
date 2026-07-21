import { describe, expect, it } from "vitest";
import { isAgentLinkLocation, safeRedirectUrl, signInUrlFor } from "./AuthPage";

describe("auth routes", () => {

  it("returns an approved agent user to their pending approval link", () => {
    expect(signInUrlFor("/agent-link", "?token=abc", "#approve")).toBe(
      "/access?redirect_url=%2Fagent-link%3Ftoken%3Dabc%23approve",
    );
    expect(safeRedirectUrl("?redirect_url=%2Fagent-link%3Ftoken%3Dabc%23approve")).toBe(
      "/agent-link?token=abc#approve",
    );
  });

  it("keeps legacy hash-based installer links on the approval route", () => {
    const hash = "#/agent-link?callback=http%3A%2F%2F127.0.0.1%3A4242%2Fcallback&state=abc";
    expect(isAgentLinkLocation("/", hash)).toBe(true);
    expect(signInUrlFor("/", "", hash)).toBe(
      "/access?redirect_url=%2F%23%2Fagent-link%3Fcallback%3Dhttp%253A%252F%252F127.0.0.1%253A4242%252Fcallback%26state%3Dabc",
    );
    expect(safeRedirectUrl("?redirect_url=%2F%23%2Fagent-link%3Fcallback%3Dhttp%253A%252F%252F127.0.0.1%253A4242%252Fcallback%26state%3Dabc")).toBe(
      "/#/agent-link?callback=http%3A%2F%2F127.0.0.1%3A4242%2Fcallback&state=abc",
    );
  });

  it("does not permit an external post-sign-in redirect", () => {
    expect(safeRedirectUrl("?redirect_url=https%3A%2F%2Fevil.example")).toBe("/dashboard");
    expect(safeRedirectUrl("?redirect_url=%2F%2Fevil.example")).toBe("/dashboard");
  });
});
