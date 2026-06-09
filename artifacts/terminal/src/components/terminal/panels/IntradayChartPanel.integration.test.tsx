// @vitest-environment jsdom
//
// Locks in the intraday chart's in-panel Resolution + Window controls against
// regressions. The controls were only ever verified once by a manual UI test;
// because orchestration routing to the intraday panel is stochastic (LLM-driven)
// a future change could silently break the controls. This test drives the REAL
// running stack end to end:
//
//   1. Boots the FastAPI app (same `python -m uvicorn` invocation the smoke check
//      uses), exactly how the deployed server runs.
//   2. POSTs /api/orchestrate with the reliable intraday trigger phrase, RETRYING
//      until an `intraday_chart` panel comes back (routing is non-deterministic).
//   3. Renders the production <PanelContainer> wired to the live API (its control
//      clicks fire the real `POST /api/refine` with explicit `{symbol, interval,
//      range}` params — the deterministic in-panel-control contract).
//   4. Asserts the Resolution + Window rows render with the right options, that
//      clicking a control re-fetches in place (selected button highlights, chart
//      updates), and that an invalid combination (1m + 1Y) shows the
//      "Intraday Data Unavailable" state with controls still visible, then
//      recovers when a valid window is chosen.
//
// NOTE: like the api-server smoke check, the live yfinance fetch can trip the
// agent shell's MAX_PATH syscall wrapper when run from the agent's bash tool.
// It runs cleanly under the `panel-runtime-test` validation workflow (the same
// environment the `smoke`/`voice-backend` python validations make live calls in).
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React, { useState } from "react";
import { render, screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Panel } from "@workspace/api-client-react";
import { setBaseUrl } from "@workspace/api-client-react";

import { PanelContainer } from "../PanelContainer";

// recharts' ResponsiveContainer needs ResizeObserver, which jsdom doesn't
// provide. A no-op stub is enough — we assert on data-driven text/controls, not
// rendered chart geometry.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// artifacts/terminal/src/components/terminal/panels -> repo root
const repoRoot = path.resolve(__dirname, "..", "..", "..", "..", "..", "..");
const apiServerDir = path.join(repoRoot, "artifacts", "api-server");

const PORT = Number(process.env.INTRADAY_TEST_PORT ?? 8242);
const BASE = `http://127.0.0.1:${PORT}`;
const TRIGGER = "intraday OHLCV chart for AAPL at 5-minute resolution";

let server: ChildProcess | null = null;

/** Boot the FastAPI app the same way scripts/smoke-api.sh does and wait for health. */
async function bootServer(): Promise<void> {
  server = spawn(
    "python",
    [
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(PORT),
      "--app-dir",
      apiServerDir,
    ],
    {
      cwd: repoRoot,
      // Skip the continuous live-ingestion worker: this test only needs the
      // request path, not hundreds of background fetches.
      env: { ...process.env, TERMINAL_SKIP_WORKER: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let log = "";
  server.stdout?.on("data", (d) => (log += d.toString()));
  server.stderr?.on("data", (d) => (log += d.toString()));
  server.on("exit", (code) => {
    if (code && code !== 0) {
      // Surface the boot log if the process dies during startup.
      console.error(`api-server exited with code ${code}\n${log}`);
    }
  });

  for (let i = 0; i < 60; i++) {
    if (server.exitCode != null) {
      throw new Error(`api-server exited during startup (code ${server.exitCode})\n${log}`);
    }
    try {
      const res = await fetch(`${BASE}/api/healthz`);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`api-server did not become healthy within 60s\n${log}`);
}

interface OrchestrateResult {
  sessionId: string;
  panel: Panel;
}

/** POST the trigger phrase, retrying until an intraday_chart panel is returned. */
async function acquireIntradayPanel(attempts = 6): Promise<OrchestrateResult> {
  let lastTypes: string[] = [];
  for (let i = 0; i < attempts; i++) {
    const sessionId = `intraday-it-${Date.now()}-${i}`;
    const res = await fetch(`${BASE}/api/orchestrate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: TRIGGER, sessionId }),
    });
    if (!res.ok) continue;
    const body = (await res.json()) as { sessionId: string; panels: Panel[] };
    const panels = body.panels ?? [];
    lastTypes = panels.map((p) => p.type);
    const panel = panels.find((p) => p.type === "intraday_chart");
    if (panel) return { sessionId: body.sessionId ?? sessionId, panel };
  }
  throw new Error(
    `orchestrate never routed to an intraday_chart panel after ${attempts} attempts ` +
      `(last panel types: ${JSON.stringify(lastTypes)})`,
  );
}

/**
 * Stateful host that mirrors how Terminal mounts a panel: it owns the panel and
 * swaps it for the refined version PanelContainer hands back, so a control click
 * round-trips through the real /api/refine endpoint and re-renders in place.
 */
function PanelHost({ initial, sessionId }: { initial: Panel; sessionId: string }) {
  const [panel, setPanel] = useState<Panel>(initial);
  return (
    <PanelContainer panel={panel} sessionId={sessionId} onRefined={setPanel} />
  );
}

function renderHost(initial: Panel, sessionId: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PanelHost initial={initial} sessionId={sessionId} />
    </QueryClientProvider>,
  );
}

/** Find a control button by its exact visible label within a labeled row. */
function controlButton(rowLabel: string, value: string): HTMLButtonElement {
  const label = screen.getByText(rowLabel);
  const row = label.parentElement as HTMLElement;
  return within(row).getByRole("button", { name: value }) as HTMLButtonElement;
}

const ACTIVE = /bg-white/; // active segment style adds "text-black bg-white border-white"

describe("intraday chart in-panel controls (live)", () => {
  beforeAll(async () => {
    await bootServer();
    setBaseUrl(BASE);
  }, 90_000);

  afterAll(() => {
    setBaseUrl(null);
    cleanup();
    if (server && server.exitCode == null) {
      server.kill("SIGTERM");
    }
  });

  it(
    "renders Resolution + Window rows, re-fetches on click, and handles an invalid combo",
    async () => {
      const { panel, sessionId } = await acquireIntradayPanel();
      expect(panel.type).toBe("intraday_chart");
      const initialData = panel.data as any;
      expect(initialData.symbol).toBe("AAPL");
      expect(initialData.available).toBe(true);

      renderHost(panel, sessionId);

      // --- control rows render with the right options ---
      expect(screen.getByText("Resolution")).toBeTruthy();
      expect(screen.getByText("Window")).toBeTruthy();
      for (const r of ["1m", "5m", "15m", "30m", "1H"]) {
        expect(controlButton("Resolution", r)).toBeTruthy();
      }
      for (const w of ["1D", "5D", "1M", "3M", "6M", "1Y"]) {
        expect(controlButton("Window", w)).toBeTruthy();
      }

      // --- click a resolution -> live refine -> chart updates in place ---
      fireEvent.click(controlButton("Resolution", "15m"));
      await waitFor(
        () => {
          expect(controlButton("Resolution", "15m").className).toMatch(ACTIVE);
          // the served interval label is data-driven, proving a real re-fetch
          expect(screen.getByText("15-minute")).toBeTruthy();
        },
        { timeout: 30_000 },
      );

      // --- switch to 1m (still a valid small window) so we can build 1m + 1Y ---
      fireEvent.click(controlButton("Resolution", "1m"));
      await waitFor(
        () => {
          expect(controlButton("Resolution", "1m").className).toMatch(ACTIVE);
          expect(screen.getByText("1-minute")).toBeTruthy();
        },
        { timeout: 30_000 },
      );

      // --- invalid combination: 1m + 1Y is beyond the source limit ---
      fireEvent.click(controlButton("Window", "1Y"));
      await waitFor(
        () => {
          expect(screen.getByText("Intraday Data Unavailable")).toBeTruthy();
        },
        { timeout: 30_000 },
      );
      // controls stay visible (and reflect the attempted selection) so the user can recover
      expect(controlButton("Resolution", "1m")).toBeTruthy();
      expect(controlButton("Window", "1Y").className).toMatch(ACTIVE);

      // --- recover: a valid window for 1m brings the chart back ---
      fireEvent.click(controlButton("Window", "1D"));
      await waitFor(
        () => {
          expect(screen.queryByText("Intraday Data Unavailable")).toBeNull();
          expect(controlButton("Window", "1D").className).toMatch(ACTIVE);
          expect(screen.getByText("1-minute")).toBeTruthy();
        },
        { timeout: 30_000 },
      );
    },
    180_000,
  );
});
