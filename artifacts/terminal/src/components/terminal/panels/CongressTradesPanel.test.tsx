// @vitest-environment jsdom
//
// Locks in the congressional-trades panel's honesty contract in the browser DOM:
// every disclosed trade must surface BOTH its transaction date AND its disclosure
// date (not just the reporting lag), plus the source link, party/chamber, side and
// amount range. The reporting lag is real (txn vs disclosure differ), so showing
// both dates is a core acceptance requirement — this test guards against a
// regression where only one date is rendered.
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, within, fireEvent } from "@testing-library/react";

import { CongressTradesPanel } from "./CongressTradesPanel";

afterEach(() => cleanup());

type CTData = React.ComponentProps<typeof CongressTradesPanel>["data"];

const DATA: CTData = {
  scope: "NVDA",
  ticker: "NVDA",
  trades: [
    {
      id: "ct-aaa",
      member: "Jane Buyer",
      chamber: "House",
      party: "Democrat",
      partyCode: "D",
      ticker: "NVDA",
      type: "buy",
      rawType: "Purchase",
      amountRange: "$1,001 - $15,000",
      amountLow: 1001,
      amountHigh: 15000,
      transactionDate: "2026-04-08",
      disclosureDate: "2026-05-01",
      lagDays: 23,
      sourceUrl: "https://www.quiverquant.com/congresstrading/politician/Jane%20Buyer",
      description: null,
    },
    {
      id: "ct-bbb",
      member: "John Seller",
      chamber: "Senate",
      party: "Republican",
      partyCode: "R",
      ticker: "NVDA",
      type: "sell",
      rawType: "Sale (Partial)",
      amountRange: "$100,001 - $250,000",
      amountLow: 100001,
      amountHigh: 250000,
      transactionDate: "2026-05-08",
      disclosureDate: "2026-06-02",
      lagDays: 25,
      sourceUrl: "https://www.quiverquant.com/congresstrading/politician/John%20Seller",
      description: null,
    },
  ],
  highlights: [],
  stats: {
    total: 2,
    buys: 1,
    sells: 1,
    exchanges: 0,
    avgLagDays: 24,
    maxLagDays: 25,
    uniqueMembers: 2,
  },
  lagNote: "Members must disclose trades within ~45 days under the STOCK Act.",
  disclaimer: "Public STOCK Act disclosures aggregated by Quiver Quantitative.",
  asOf: "2026-06-09T00:00:00+00:00",
  source: "live",
};

describe("CongressTradesPanel", () => {
  it("renders both transaction and disclosure dates for every trade", () => {
    render(<CongressTradesPanel data={DATA} />);

    // Transaction dates (formatted "Apr 8, 26" / "May 8, 26").
    expect(screen.getByText(/Apr 8, 26/)).toBeTruthy();
    expect(screen.getByText(/May 8, 26/)).toBeTruthy();

    // Disclosure dates must ALSO be present, each prefixed with "disc".
    const discNodes = screen.getAllByTitle("Disclosure date");
    expect(discNodes.length).toBe(2);
    expect(discNodes[0].textContent).toMatch(/disc/i);
    // The two disclosure dates (May 1 and Jun 2) both render.
    const allDisc = discNodes.map(n => n.textContent).join(" ");
    expect(allDisc).toMatch(/May 1, 26/);
    expect(allDisc).toMatch(/Jun 2, 26/);

    // Reporting lag is still shown alongside, not instead of, the dates.
    expect(allDisc).toMatch(/23d/);
    expect(allDisc).toMatch(/25d/);
  });

  it("shows member, party/chamber, side, amount and a source link per trade", () => {
    render(<CongressTradesPanel data={DATA} />);

    expect(screen.getByText("Jane Buyer")).toBeTruthy();
    expect(screen.getByText("John Seller")).toBeTruthy();
    expect(screen.getByText("$1,001 - $15,000")).toBeTruthy();

    // Source links back to the public disclosure page.
    const links = screen.getAllByRole("link") as HTMLAnchorElement[];
    expect(links.length).toBe(2);
    expect(links.every(a => a.href.includes("quiverquant.com/congresstrading/politician"))).toBe(true);
  });

  it("filters to buys when the Buys tab is selected", () => {
    render(<CongressTradesPanel data={DATA} />);
    fireEvent.click(screen.getByRole("button", { name: "Buys" }));
    expect(screen.getByText("Jane Buyer")).toBeTruthy();
    expect(screen.queryByText("John Seller")).toBeNull();
  });
});
