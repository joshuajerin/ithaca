// @vitest-environment jsdom
//
// Exercises the supply-chain drill-down INTERACTION in the browser DOM — the
// part the standalone backend test (tests/test_supply_chain_drilldown.py) does
// not cover: clicking a counterparty with a symbol recenters the panel, the
// breadcrumb trail appears and truncates on Back, and the risk summary updates
// for the new subject.
//
// The real wiring (PanelContainer.tsx, line ~266) passes
//   onRecenter={(symbol) => submitRefine(`Recenter supply chain on ${symbol}`)}
// which round-trips through POST /api/refine and feeds the rebuilt panel back in
// as new `data`. This test stands in a fixture-backed parent for that round-trip
// (symbol -> rebuilt SupplyChainData), so it verifies the UI contract without a
// live backend: a drill swaps `data`, and the panel reacts.
import { describe, it, expect, afterEach } from "vitest";
import { useState } from "react";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";

import { SupplyChainPanel } from "./SupplyChainPanel";

afterEach(() => cleanup());

type SCData = React.ComponentProps<typeof SupplyChainPanel>["data"];

// Two fully-formed subjects. Drilling from AAPL into its supplier TSM must land
// on the TSM fixture (a different subject, different counterparties, different
// risk summary), and Back must return to AAPL.
const AAPL: SCData = {
  symbol: "AAPL",
  name: "Apple Inc",
  nodes: [
    { id: "AAPL", name: "Apple Inc", symbol: "AAPL", role: "subject", exposure: 100, country: "US" },
    { id: "TSM", name: "Taiwan Semiconductor", symbol: "TSM", role: "supplier", exposure: 35, country: "TW", riskScore: "Critical", riskValue: 90, singleSource: true },
    { id: "FOXCONN", name: "Foxconn Assembly", symbol: null, role: "supplier", exposure: 25, country: "CN", riskScore: "High", riskValue: 70 },
    { id: "BBY", name: "Best Buy", symbol: "BBY", role: "customer", exposure: 15, country: "US", riskScore: "Low" },
  ],
  edges: [
    { source: "TSM", target: "AAPL", weight: 35 },
    { source: "FOXCONN", target: "AAPL", weight: 25 },
    { source: "AAPL", target: "BBY", weight: 15 },
  ],
  table: [
    { name: "Taiwan Semiconductor", symbol: "TSM", role: "supplier", exposure: 35, country: "TW", category: "Foundry", riskScore: "Critical", riskValue: 90, singleSource: true },
    { name: "Foxconn Assembly", symbol: null, role: "supplier", exposure: 25, country: "CN", category: "Assembly", riskScore: "High", riskValue: 70 },
    { name: "Best Buy", symbol: "BBY", role: "customer", exposure: 15, country: "US", category: "Retail", riskScore: "Low" },
  ],
  riskSummary: {
    topRisks: [
      { kind: "concentration", title: "Foundry Concentration", detail: "Sole-source foundry for advanced chips", level: "Critical", riskValue: 90 },
    ],
    countryConcentration: [
      { country: "TW", countryName: "Taiwan", sharePct: 35, geoRisk: 0.8 },
    ],
    counts: { Low: 1, Medium: 0, High: 1, Critical: 1 },
  },
};

const TSM: SCData = {
  symbol: "TSM",
  name: "Taiwan Semiconductor",
  nodes: [
    { id: "TSM", name: "Taiwan Semiconductor", symbol: "TSM", role: "subject", exposure: 100, country: "TW" },
    { id: "ASML", name: "ASML Holding", symbol: "ASML", role: "supplier", exposure: 40, country: "NL", riskScore: "High", riskValue: 75, singleSource: true },
    { id: "AAPL", name: "Apple Inc", symbol: "AAPL", role: "customer", exposure: 30, country: "US", riskScore: "Medium" },
  ],
  edges: [
    { source: "ASML", target: "TSM", weight: 40 },
    { source: "TSM", target: "AAPL", weight: 30 },
  ],
  table: [
    { name: "ASML Holding", symbol: "ASML", role: "supplier", exposure: 40, country: "NL", category: "Lithography", riskScore: "High", riskValue: 75, singleSource: true },
    { name: "Apple Inc", symbol: "AAPL", role: "customer", exposure: 30, country: "US", category: "Devices", riskScore: "Medium" },
  ],
  riskSummary: {
    topRisks: [
      { kind: "concentration", title: "Lithography Concentration", detail: "Sole EUV lithography supplier", level: "High", riskValue: 75 },
    ],
    countryConcentration: [
      { country: "NL", countryName: "Netherlands", sharePct: 40, geoRisk: 0.4 },
    ],
    counts: { Low: 0, Medium: 1, High: 1, Critical: 0 },
  },
};

const FIXTURES: Record<string, SCData> = { AAPL, TSM };

// Stand-in for PanelContainer: onRecenter resolves the rebuilt panel for the
// requested symbol (the effect a /api/refine round-trip has) and swaps `data`.
// Records every recenter call so tests can assert the click target fired.
function Harness({
  initial,
  onRecenterSpy,
}: {
  initial: SCData;
  onRecenterSpy: (symbol: string) => void;
}) {
  const [data, setData] = useState<SCData>(initial);
  return (
    <SupplyChainPanel
      data={data}
      onRecenter={(symbol) => {
        onRecenterSpy(symbol);
        const next = FIXTURES[symbol.toUpperCase()];
        if (next) setData(next);
      }}
    />
  );
}

/** The panel header reads "<SYMBOL> · <Name> Supply Chain"; assert the subject. */
function expectSubject(symbol: string, name: string) {
  expect(screen.getByText(`${name} Supply Chain`)).toBeTruthy();
  const headers = screen.getAllByText(symbol);
  expect(headers.length).toBeGreaterThan(0);
}

describe("SupplyChainPanel drill-down", () => {
  it("recenters on a supplier with a symbol when its row is clicked", () => {
    const calls: string[] = [];
    render(<Harness initial={AAPL} onRecenterSpy={(s) => calls.push(s)} />);

    // Starts on AAPL with no breadcrumb (trail length 1).
    expectSubject("AAPL", "Apple Inc");
    expect(screen.queryByText("Back")).toBeNull();
    expect(screen.getByText("Sole-source foundry for advanced chips")).toBeTruthy();

    // Click the clickable supplier (TSM has a symbol) in the Top Suppliers list.
    fireEvent.click(screen.getByText("Taiwan Semiconductor"));

    // onRecenter fired with the upper-cased symbol, and the panel recentered.
    expect(calls).toEqual(["TSM"]);
    expectSubject("TSM", "Taiwan Semiconductor");
  });

  it("shows a breadcrumb and Back returns to the prior subject", () => {
    render(<Harness initial={AAPL} onRecenterSpy={() => {}} />);

    fireEvent.click(screen.getByText("Taiwan Semiconductor"));

    // Breadcrumb appears with the trail AAPL > TSM and a Back control.
    expect(screen.getByText("Back")).toBeTruthy();
    const crumb = screen.getByText("Back").closest("div")!;
    expect(within(crumb).getByText("AAPL")).toBeTruthy();
    expect(within(crumb).getByText("TSM")).toBeTruthy();

    // Back returns to AAPL and collapses the breadcrumb (trail length 1).
    fireEvent.click(screen.getByText("Back"));
    expectSubject("AAPL", "Apple Inc");
    expect(screen.queryByText("Back")).toBeNull();
  });

  it("updates the risk summary for the new subject after a drill", () => {
    render(<Harness initial={AAPL} onRecenterSpy={() => {}} />);

    // AAPL's risk summary: Critical present, foundry detail shown.
    expect(screen.getByText("Sole-source foundry for advanced chips")).toBeTruthy();
    expect(screen.getByText("1 Critical")).toBeTruthy();

    fireEvent.click(screen.getByText("Taiwan Semiconductor"));

    // TSM's risk summary replaces it: different top risk, no Critical bucket.
    expect(screen.getByText("Sole EUV lithography supplier")).toBeTruthy();
    expect(screen.queryByText("Sole-source foundry for advanced chips")).toBeNull();
    expect(screen.queryByText("1 Critical")).toBeNull();
  });

  it("does not recenter when a counterparty has no symbol", () => {
    const calls: string[] = [];
    render(<Harness initial={AAPL} onRecenterSpy={(s) => calls.push(s)} />);

    // Foxconn has no symbol -> not a drill target.
    fireEvent.click(screen.getByText("Foxconn Assembly"));

    expect(calls).toEqual([]);
    expectSubject("AAPL", "Apple Inc");
    expect(screen.queryByText("Back")).toBeNull();
  });

  it("recenters from a row in the table view as well", () => {
    const calls: string[] = [];
    render(<Harness initial={AAPL} onRecenterSpy={(s) => calls.push(s)} />);

    // Switch to the table tab and click the TSM row.
    fireEvent.click(screen.getByText("table"));
    const cell = screen.getByText("Taiwan Semiconductor");
    fireEvent.click(cell.closest("tr")!);

    expect(calls).toEqual(["TSM"]);
    expectSubject("TSM", "Taiwan Semiconductor");
  });
});
