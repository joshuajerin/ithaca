import { describe, expect, it } from "vitest";
import { shouldUseClerkApiToken } from "./config";

describe("local API authentication mode", () => {
  it("uses the local tenant fallback in Vite dev by default", () => {
    expect(shouldUseClerkApiToken(true, undefined)).toBe(false);
  });

  it("keeps Clerk bearer auth enabled outside local dev", () => {
    expect(shouldUseClerkApiToken(false, undefined)).toBe(true);
  });

  it("allows an explicit local Clerk auth override", () => {
    expect(shouldUseClerkApiToken(true, "true")).toBe(true);
  });

  it("accepts explicit false and trims override values", () => {
    expect(shouldUseClerkApiToken(false, " false ")).toBe(false);
    expect(shouldUseClerkApiToken(true, " TRUE ")).toBe(true);
  });
});
