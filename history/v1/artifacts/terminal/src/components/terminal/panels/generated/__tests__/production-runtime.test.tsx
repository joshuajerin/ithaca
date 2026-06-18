// @vitest-environment jsdom
//
// Verifies the PRODUCTION loading path for AI-generated panels — the path that
// cannot be exercised by the dev server (which relies on Vite HMR /
// `import.meta.glob`). In a built/deployed app, a panel authored after the
// build is not in the bundle; the frontend fetches its TSX source from
// `GET /api/generated-panels`, transpiles it with sucrase in the browser,
// evaluates it into a React component, and falls back to the generic JSON
// renderer if that fails.
//
// The test panel type is written AFTER this module (and the registry it imports)
// is evaluated, so it is never in the static `import.meta.glob` registry — which
// is exactly the state a production runtime is in for a panel authored after the
// build, forcing the runtime fetch+compile path.
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { render, screen, waitFor, cleanup } from "@testing-library/react";

import { DynamicPanel } from "../DynamicPanel";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// The generated-panel directory and the terminal package root, derived from
// this test file's location so the test is independent of the cwd it runs in.
const generatedDir = path.resolve(__dirname, "..");
const terminalRoot = path.resolve(generatedDir, "..", "..", "..", "..", "..");

// A panel "authored after the build": its source (and this marker) must never
// appear in the production bundle, so the only way the app can render it is via
// the runtime fetch + compile path.
const PANEL_TYPE = "autotest_runtime_panel";
const RUNTIME_MARKER = "RUNTIME_COMPILE_OK_4Z9";
const freshPanelPath = path.join(generatedDir, `${PANEL_TYPE}.tsx`);
const FRESH_PANEL_SOURCE = `import React from "react";

export default function AutotestRuntimePanel({ data }: { data: any }) {
  const headline = data?.headline ?? "";
  return (
    <div data-testid="runtime-compiled" className="text-white">
      <span className="editorial-label">${RUNTIME_MARKER}</span>
      <span>{headline}</span>
    </div>
  );
}
`;

function readBundle(): string {
  const assetsDir = path.join(terminalRoot, "dist", "public", "assets");
  if (!fs.existsSync(assetsDir)) return "";
  return fs
    .readdirSync(assetsDir)
    .filter((f) => f.endsWith(".js"))
    .map((f) => fs.readFileSync(path.join(assetsDir, f), "utf8"))
    .join("\n");
}

describe("production runtime panel loading", () => {
  beforeAll(() => {
    // Ensure a stale copy from a previous crashed run isn't present at build
    // time (which would wrongly bundle it).
    if (fs.existsSync(freshPanelPath)) fs.rmSync(freshPanelPath);

    // 1) Produce a real production build.
    execSync("pnpm run build", {
      cwd: terminalRoot,
      env: { ...process.env, PORT: "5000", BASE_PATH: "/" },
      stdio: "pipe",
      timeout: 150_000,
    });

    // 2) Write a fresh generated panel AFTER the build — so it is provably
    //    absent from the bundle and can only load via the runtime path.
    fs.writeFileSync(freshPanelPath, FRESH_PANEL_SOURCE, "utf8");
  }, 180_000);

  afterAll(() => {
    if (fs.existsSync(freshPanelPath)) fs.rmSync(freshPanelPath);
  });

  it("excludes a panel authored after the build from the production bundle", () => {
    expect(
      fs.existsSync(path.join(terminalRoot, "dist", "public", "index.html")),
      "production build should have produced dist/public/index.html",
    ).toBe(true);
    const bundle = readBundle();
    expect(bundle.length, "production bundle JS should not be empty").toBeGreaterThan(0);
    expect(
      bundle.includes(RUNTIME_MARKER),
      "a panel written after the build must NOT be in the production bundle",
    ).toBe(false);
  });

  it("renders the runtime-compiled component (not the generic fallback)", async () => {
    const source = fs.readFileSync(freshPanelPath, "utf8");
    const original = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ panels: [{ panelType: PANEL_TYPE, source }] }), {
        headers: { "content-type": "application/json" },
      })) as typeof fetch;

    try {
      render(
        <DynamicPanel type={PANEL_TYPE} data={{ headline: "hello-from-data" }} />,
      );

      const el = await screen.findByTestId("runtime-compiled");
      expect(el.textContent ?? "").toMatch(new RegExp(RUNTIME_MARKER));
      expect(el.textContent ?? "").toMatch(/hello-from-data/);
    } finally {
      globalThis.fetch = original;
      cleanup();
    }
  });

  it("falls back to the generic renderer when a generated panel fails to compile", async () => {
    const cases: { type: string; source: string }[] = [
      {
        // Disallowed import — rejected by the require shim during evaluation.
        type: "autotest_disallowed_import",
        source:
          'import React from "react";\nimport bad from "not-allowed-lib";\nexport default function B({ data }: { data: any }) { return <div>{String(bad)}</div>; }',
      },
      {
        // Missing default export — compileComponent throws.
        type: "autotest_no_default",
        source:
          'import React from "react";\nexport function NotDefault({ data }: { data: any }) { return <div>{data?.metric_label}</div>; }',
      },
      {
        // Broken syntax — transpile throws.
        type: "autotest_broken_syntax",
        source: 'import React from "react";\nexport default function ( {',
      },
    ];

    for (const c of cases) {
      const original = globalThis.fetch;
      const originalError = console.error;
      const errors: unknown[] = [];
      console.error = (...args: unknown[]) => {
        errors.push(args);
      };
      globalThis.fetch = (async () =>
        new Response(JSON.stringify({ panels: [{ panelType: c.type, source: c.source }] }), {
          headers: { "content-type": "application/json" },
        })) as typeof fetch;

      try {
        render(
          <DynamicPanel type={c.type} data={{ metric_label: "GENERIC_FALLBACK_OK" }} />,
        );

        // The generic JSON renderer surfaces the data — not a blank/crashed panel.
        await waitFor(() => {
          expect(
            screen.queryByText(/GENERIC_FALLBACK_OK/),
            `generic fallback should render data for case "${c.type}"`,
          ).not.toBeNull();
        });
        // It must be the generic renderer, not a compiled component nor the
        // hard "Panel render error" state.
        expect(
          screen.queryByTestId("runtime-compiled"),
          `case "${c.type}" must not render a compiled component`,
        ).toBeNull();
        expect(
          screen.queryByText(/Panel render error/),
          `case "${c.type}" must not show the hard error state`,
        ).toBeNull();
      } finally {
        globalThis.fetch = original;
        console.error = originalError;
        cleanup();
      }
    }
  });
});
