import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CompliancePanel } from "./components/terminal/panels/CompliancePanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const initial = {
  limits: {
    maxPositionPct: 15,
    maxNetPct: 120,
    maxLeverage: 2,
    maxConcentrationPct: 50,
  },
  limitDefs: [
    { key: "maxPositionPct", label: "Max position", unit: "%", help: "test" },
  ],
  restricted: ["GME"],
  watch: [],
  policyConfigured: true,
  limitsEnforced: false,
  policyVersion: 7,
  killSwitch: false,
  killSource: "none" as const,
  killVersion: 0,
  strategies: [],
  audit: [],
  check: null,
};

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("CompliancePanel", () => {
  it("sends the policy version and renders a stale-write conflict", async () => {
    let reads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      if (String(input) === "/api/compliance") {
        reads += 1;
        return new Response(
          JSON.stringify(reads === 1 ? initial : { ...initial, policyVersion: 8 }),
          { status: 200 },
        );
      }
      return new Response(
        JSON.stringify({ detail: "compliance policy version is 8, expected 7" }),
        { status: 409 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<CompliancePanel data={initial} />);
    });

    const add = container.querySelector<HTMLButtonElement>(
      'button[aria-label="Add restricted name"]',
    );
    const form = add?.closest("form");
    const input = form?.querySelector<HTMLInputElement>("input");
    expect(add).not.toBeNull();
    expect(form).not.toBeNull();
    expect(input).not.toBeNull();

    await act(async () => {
      if (input) {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(
          input,
          "TSLA",
        );
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
    await act(async () => {
      form?.requestSubmit();
    });

    const mutation = fetchMock.mock.calls.find(
      ([url]) => String(url) === "/api/compliance/restricted",
    );
    expect(mutation).toBeDefined();
    const mutationInit = mutation?.[1] as RequestInit | undefined;
    expect(JSON.parse(String(mutationInit?.body))).toEqual({
      symbol: "TSLA",
      expect_version: 7,
    });
    expect(container.textContent).toContain("compliance policy version is 8, expected 7");
    expect(reads).toBe(2);

    await act(async () => root.unmount());
  });
});
