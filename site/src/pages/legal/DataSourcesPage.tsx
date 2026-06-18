import LegalLayout from "./LegalLayout";

export default function DataSourcesPage() {
  return (
    <LegalLayout
      title="Data Sources"
      subtitle="Where our data comes from, how fresh it is, and what we don't have yet."
      effectiveDate="June 18, 2026"
      lastUpdated="June 18, 2026"
      sections={[
        {
          heading: "Overview",
          content: (
            <div>
              <p>Doomberg's data layer is built on a combination of public filings, open APIs, and a historical data archive collected from public sources. We believe in being transparent about exactly where data comes from, because data provenance directly affects how you should interpret it.</p>
              <p className="mt-3">All data in the Platform carries a <strong>provenance envelope</strong> — metadata that identifies the source, the data's freshness, and whether it is point-in-time accurate. Skills that return data from our archive will indicate <code className="bg-sand/60 px-1 py-0.5 rounded text-[0.82em] font-mono">source: "doomberg-v1-archive"</code>. Live data fetched at query time will indicate the originating source.</p>
            </div>
          ),
        },
        {
          heading: "Price Data (OHLCV)",
          content: (
            <div>
              <div className="rounded border border-line p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Source</p>
                    <p className="mt-1 font-semibold">Yahoo Finance (yfinance)</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Freshness</p>
                    <p className="mt-1 font-semibold text-olive">Live (on demand)</p>
                  </div>
                </div>
              </div>
              <p className="mt-3">OHLCV (open, high, low, close, volume) data is fetched on demand from Yahoo Finance's public API. This includes daily and intraday price history for US equities, ETFs, and major indices. Yahoo Finance data is generally reliable for historical analysis but may contain adjustments, splits, or gaps. It is <strong>not</strong> a professional-grade data feed.</p>
              <p className="mt-3"><strong>Archive:</strong> We maintain a static historical archive of 81,832 OHLCV records for the tracked universe, collected prior to June 2026. This archive supplements live fetches and is used as the default for backtesting.</p>
              <p className="mt-3"><strong>Limitations:</strong> Yahoo Finance data can experience outages, be delayed, or occasionally return incorrect adjusted prices. This data is not suitable for high-frequency or execution-critical applications. Options, futures, and forex data coverage is limited.</p>
            </div>
          ),
        },
        {
          heading: "Institutional Holdings (13F)",
          content: (
            <div>
              <div className="rounded border border-line p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Source</p>
                    <p className="mt-1 font-semibold">SEC EDGAR</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Freshness</p>
                    <p className="mt-1 font-semibold text-warn">Archive snapshot (pre-June 2026)</p>
                  </div>
                </div>
              </div>
              <p className="mt-3">Institutional holdings data comes from Form 13F filings submitted to the SEC by institutional investment managers with &gt;$100M in assets under management. Our archive contains 134,349 holdings records and 32 filing records sourced from public EDGAR data.</p>
              <p className="mt-3"><strong>Limitations:</strong> 13F filings are submitted quarterly, with a 45-day reporting lag. Holdings reflect end-of-quarter positions, not real-time positions. Managers may have substantially changed positions between the filing date and the public release. Positions under $200,000 may be omitted. Our data is a static snapshot and is not updated in real time.</p>
            </div>
          ),
        },
        {
          heading: "Congressional Trading",
          content: (
            <div>
              <div className="rounded border border-line p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Source</p>
                    <p className="mt-1 font-semibold">House / Senate eFD Public Filings</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Freshness</p>
                    <p className="mt-1 font-semibold text-warn">Archive snapshot (pre-June 2026)</p>
                  </div>
                </div>
              </div>
              <p className="mt-3">Congressional trading disclosures come from the STOCK Act financial disclosure system. House members file through the House Clerk's electronic financial disclosure (eFD) portal; Senators file through a separate Senate system. Our archive contains 1,002 trade records.</p>
              <p className="mt-3"><strong>Limitations:</strong> Members have up to 45 days to disclose trades under the STOCK Act, creating inherent reporting lag. Some disclosures are submitted as paper filings and may not appear in our archive. Transaction amounts are reported as ranges, not exact figures. Our data is a static snapshot.</p>
            </div>
          ),
        },
        {
          heading: "Insider Transactions",
          content: (
            <div>
              <div className="rounded border border-line p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Source</p>
                    <p className="mt-1 font-semibold">SEC EDGAR — Form 4 / Form 5</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Freshness</p>
                    <p className="mt-1 font-semibold text-warn">Archive snapshot (pre-June 2026)</p>
                  </div>
                </div>
              </div>
              <p className="mt-3">Insider transaction data comes from Form 4 and Form 5 filings submitted to the SEC by corporate insiders (directors, officers, and 10%+ shareholders). Our archive contains 14,376 transaction records.</p>
              <p className="mt-3"><strong>Limitations:</strong> Insiders have 2 business days to file Form 4 after a transaction. Some transactions involve options or complex derivative instruments that may be difficult to interpret. Our data is a static snapshot and does not include real-time filings.</p>
            </div>
          ),
        },
        {
          heading: "Fundamentals",
          content: (
            <div>
              <div className="rounded border border-line p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Source</p>
                    <p className="mt-1 font-semibold">yfinance / Public APIs + Internal Archive</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Freshness</p>
                    <p className="mt-1 font-semibold text-warn">Mixed (live + archive snapshot)</p>
                  </div>
                </div>
              </div>
              <p className="mt-3">Fundamental data (P/E ratios, revenue, EPS, market cap, etc.) is sourced from a combination of live yfinance queries and our historical archive of 671 fundamental records and 903 point-in-time fundamental records.</p>
              <p className="mt-3"><strong>Point-in-time data:</strong> Our <code className="bg-sand/60 px-1 py-0.5 rounded text-[0.82em] font-mono">fundamentals.pit</code> skill provides genuine point-in-time fundamentals — the data as it was known on a given historical date, using the report's actual filing date. This is a meaningful advantage for backtesting versus using restated "as-reported" data.</p>
              <p className="mt-3"><strong>Limitations:</strong> Live fundamental data from yfinance may be delayed or incorrect. Deep historical point-in-time fundamentals are limited to the 903 records in our archive. We do not have institutional-grade fundamentals databases (Bloomberg, Compustat) and cannot guarantee the accuracy of financial model inputs.</p>
            </div>
          ),
        },
        {
          heading: "Analyst Ratings",
          content: (
            <div>
              <div className="rounded border border-line p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Source</p>
                    <p className="mt-1 font-semibold">yfinance / Public APIs</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Freshness</p>
                    <p className="mt-1 font-semibold text-warn">Archive snapshot (155 records)</p>
                  </div>
                </div>
              </div>
              <p className="mt-3">Analyst consensus ratings, price targets, and recommendation distributions are sourced from aggregated public data. Our archive contains 155 analyst rating records. Analyst ratings are inherently subject to conflicts of interest and should not be used as the sole basis for investment decisions.</p>
            </div>
          ),
        },
        {
          heading: "ETF Holdings",
          content: (
            <div>
              <div className="rounded border border-line p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Source</p>
                    <p className="mt-1 font-semibold">Public ETF provider disclosures</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Freshness</p>
                    <p className="mt-1 font-semibold text-warn">Archive snapshot (310 records)</p>
                  </div>
                </div>
              </div>
              <p className="mt-3">ETF holdings data is sourced from public disclosures by ETF providers. Our archive contains 310 ETF holding records. ETF compositions change frequently; our static archive does not reflect current holdings.</p>
            </div>
          ),
        },
        {
          heading: "Sentiment & News",
          content: (
            <div>
              <div className="rounded border border-line p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Source</p>
                    <p className="mt-1 font-semibold">Aggregated public sources</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Freshness</p>
                    <p className="mt-1 font-semibold text-warn">Archive snapshot (5,672 news + 178 sentiment)</p>
                  </div>
                </div>
              </div>
              <p className="mt-3">News headlines and sentiment scores are sourced from aggregated public news feeds and classified using automated sentiment analysis. Our archive contains 5,672 news records and 178 sentiment snapshots. This data reflects conditions prior to June 2026 and is not updated in real time.</p>
            </div>
          ),
        },
        {
          heading: "Macro Data",
          content: (
            <div>
              <div className="rounded border border-line p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Source</p>
                    <p className="mt-1 font-semibold">Public APIs (FRED, Yahoo Finance)</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-[0.75rem] uppercase tracking-wide text-faint">Freshness</p>
                    <p className="mt-1 font-semibold text-warn">Archive snapshot (30 macro records)</p>
                  </div>
                </div>
              </div>
              <p className="mt-3">Macro economic data (interest rates, indices, commodities, FX) is sourced from public data providers. Our archive contains 30 macro price/quote records.</p>
            </div>
          ),
        },
        {
          heading: "What We Don't Have",
          content: (
            <div>
              <p>We believe in being honest about gaps. The following data types are <strong>not available</strong> on the Platform:</p>
              <ul className="mt-3 space-y-3">
                {[
                  { name: "Real-time options flow & dark pool", reason: "Requires OPRA redistribution license ($5k–$50k+/month). We do not currently have this license." },
                  { name: "Tick-level historical price data", reason: "Our archive uses daily OHLCV. Intraday tick data at scale requires expensive data subscriptions." },
                  { name: "Real-time institutional positions", reason: "13F filings are quarterly with a 45-day lag by law. Real-time institutional positions are not publicly available." },
                  { name: "Corporate earnings call transcripts", reason: "Paid data product. Not currently licensed." },
                  { name: "Credit default swap (CDS) data", reason: "Not available from public sources at scale." },
                  { name: "Satellite/geospatial alternative data", reason: "Specialized paid data product. Not currently licensed." },
                ].map((item) => (
                  <li key={item.name} className="flex gap-3">
                    <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-neg/60" />
                    <div>
                      <span className="font-semibold">{item.name}:</span>{" "}
                      <span className="text-muted">{item.reason}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ),
        },
        {
          heading: "Planned Additions",
          content: (
            <div>
              <p>We are actively working to expand data coverage. Planned additions include:</p>
              <ul className="mt-2 list-disc pl-5 space-y-1">
                <li>Real-time market data via licensed exchange feeds</li>
                <li>Options chain data and real-time options flow</li>
                <li>Live fundamental data refresh (quarterly earnings updates)</li>
                <li>Additional macro/economic series</li>
                <li>Crypto market data</li>
              </ul>
              <p className="mt-3">This page will be updated as new data sources are added.</p>
            </div>
          ),
        },
        {
          heading: "No Warranty on Data Accuracy",
          content: (
            <p>All data provided through the Platform is offered "as-is" with no warranty of accuracy, completeness, timeliness, or fitness for any particular purpose. You assume all responsibility for verifying the accuracy of any data before relying on it for trading or investment decisions. See our <a href="/legal/disclosures" className="text-olive hover:underline">Financial Disclosures</a> for full risk warnings.</p>
          ),
        },
      ]}
    />
  );
}
