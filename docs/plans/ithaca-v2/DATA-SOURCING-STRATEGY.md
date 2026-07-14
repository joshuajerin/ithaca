# Ithaca v2 — Real Data Sourcing Strategy

**Status:** proposed (reworks the data decision in MASTER-PLAN §2.4 / §4 / §10) • **Date:** 2026-06-16
**Decision driver:** The founder has rejected free Yahoo data. v1/v2-draft assumed Yahoo, which forced §2.4's painful compromise — fundamental-factor backtests forbidden, the backtester flagged as one that "lies" because Yahoo is survivorship-biased, dividend-restated, and has no point-in-time vintaging. **New mandate: source official data the way professionals do — direct from exchanges and professional providers.** This doc researches how that actually works (verified against the 2025–2026 landscape, cited inline) and designs the real strategy.

> **TL;DR for the impatient.** "Direct from the exchange the way Bloomberg does it" is a multi-million-dollar/year infrastructure build (colo cages, FPGA ticker plants, per-exchange non-display + redistribution fees), and Bloomberg itself sells you a *normalized* feed rather than the raw exchange firehose. For a startup, "official quality" is achieved by buying from vendors that *themselves* take direct exchange feeds. The single highest-leverage purchase for Ithaca is **not** a real-time feed at all — it is a **point-in-time (PIT), survivorship-bias-free historical dataset** (Sharadar, then optionally CRSP/Norgate). That one purchase unblocks the headline product capability the plan currently has on the cut list: **honest fundamental-factor backtesting.** Recommendation: launch on **Sharadar (PIT research) + Databento (direct-feed prices/intraday/order-book) + Alpaca (broker-grade SIP for paper-live)**, and treat the "direct feeds + colo" endgame as a graduation trigger, not a launch requirement.

---

## 1. How Bloomberg / institutional data actually works

There are three layers in the professional pipeline. Understanding which layer you are actually buying is the whole game.

### 1.1 Layer 1 — Direct exchange feeds (raw, per-venue, un-normalized)

Each exchange generates its own proprietary feed straight off its matching engine. These are the lowest-latency, highest-fidelity source — but every venue speaks its own binary protocol and schema, so a consumer must run a per-exchange decoder and normalize the output itself.

- **Nasdaq TotalView-ITCH** (plus separate feeds for Nasdaq BX and PSX) is a full **depth-of-book** feed: every order add/modify/cancel/execution at every price level, enough to reconstruct queue position and quote lifetimes. Wire format is the **ITCH binary protocol**, disseminated as **multicast UDP** with A/B redundant lines and a separate retransmission/glimpse recovery service, sourced at the Carteret, NJ matching engine ([Nasdaq TotalView-ITCH spec](https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHSpecification.pdf), [Databento XNAS.ITCH](https://databento.com/datasets/XNAS.ITCH)). Full order-by-order tick data runs to tens of GB/day uncompressed.
- **NYSE Pillar / Integrated Feed** uses the **XDP** binary protocol over **multicast UDP**, carrying complete depth of book, all trades, security status, and opening/closing **imbalance** data, with per-channel A/B line redundancy ([NYSE XDP Integrated Feed Client Spec](https://www.nyse.com/publicdocs/nyse/data/Integrated_Feed_Client_Specification_v2.3d.pdf)).
- **Cboe** (BZX/BYX/EDGA/EDGX) publishes **PITCH** (depth) and **TOP** (top-of-book); Cboe states TOP is "less timely" than the depth feed and offers bandwidth-shaped Multicast PITCH variants ([Cboe Multicast PITCH spec](https://www.cboe.com/document/tech-spec/document/technical-specifications/cboe-titanium-u.s.-equitiesoptions-multicast-pitch-specification)).

**Key property:** these feeds are **raw and un-normalized** — different protocols (ITCH vs XDP vs PITCH), different message semantics, different symbology. "Getting data directly from the exchange" means decoding each venue's wire format and stitching them together yourself. Direct feeds also carry data the public tape omits — trade aggressor side, odd-lot quotes, auction imbalances — and odd-lots alone are nearly **50% of US equity activity not reported to the SIPs** ([Databento — proprietary feeds vs SIP](https://databento.com/blog/proprietary-feeds-vs-sip-data)).

### 1.2 Layer 2 — The consolidated SIP tapes (the regulated public price)

A **Securities Information Processor (SIP)** consolidates quotes and trades from all US exchanges and publishes the **NBBO** — the regulated, single public reference price. SIP data is **Level 1** (top-of-book best quotes + trades), aggregated across all venues. It is split across plans/tapes:
- **CTA/CQS — Tape A** (NYSE-listed) and **Tape B** (NYSE Arca/American + other non-Nasdaq listed), via CTS (trades) and CQS (quotes).
- **UTP — Tape C** (Nasdaq-listed + OTC), via UTDF/UQDF.
- (Options consolidate separately via **OPRA**.) ([Securities Information Processor — Wikipedia](https://en.wikipedia.org/wiki/Securities_information_processor), [Databento — CTA Plan](https://databento.com/microstructure/cta-plan))

**SIP modernization status (2025–2026):** The SEC's 2020 **Market Data Infrastructure Rule** (upheld by the D.C. Circuit in 2022) expanded SIP content and replaced the single-SIP model with **competing consolidators + self-aggregators** ([Sidley](https://www.sidley.com/en/insights/newsupdates/2022/06/dc-circuit-upholds-secs-market-data-infrastructure-rules-paving-the-way-for-competing-consolidators)). The three legacy plans are slated to merge into a **single CT Plan in April 2027**, with **DataCT** selected as administrator; CT Plan fee filings are under SEC review and contested (SIFMA objected Aug 2025), and **no competing consolidator is yet live at scale** ([SIFMA letter Aug 2025](https://www.sifma.org/wp-content/uploads/2025/08/SIFMA-Letter-re-Equity-Market-Data-8.25.2025.pdf), [Traders Magazine](https://www.tradersmagazine.com/am/market-data-competing-consolidators-without-ct-plan/)). Practical implication for Ithaca: the SIP landscape is mid-reform but stable enough to consume through a vendor; don't build against competing-consolidator economics yet.

**SIP latency vs direct feeds:** the SIP must aggregate from venues dispersed across the NJ data centers and adds normalization time. The CTA SIP's internal compile latency has fallen to ~15 µs, but a Carteret quote still arrives ~188 µs slower than a Mahwah quote purely from speed-of-light over ~35 miles ([Bloomberg — SIP vs Direct Feeds](https://www.bloomberg.com/professional/blog/sip-vs-direct-feeds-latency-rules/)). Net: direct feeds are single-digit microseconds; consolidated/normalized paths are milliseconds. This gap is the basis of latency-arbitrage concerns — **and it is completely irrelevant to a research-and-paper-trading platform** (see §4).

### 1.3 Layer 3 — Normalized professional feeds (how firms actually consume data)

Most firms do **not** build colo ticker plants. They buy a **managed, normalized feed**: one pre-normalized stream over a single API across hundreds of venues, with the vendor handling connectivity, decoding, normalization, symbology, entitlements, and gap recovery — trading microsecond latency for radically lower operational burden.

- **Bloomberg B-PIPE** is a consolidated normalized real-time feed aggregating ~35M instruments from 330+ exchanges and 5,000+ contributors via one API, supporting display and **non-display ("black box")** applications — explicitly so firms avoid managing direct connections to each exchange ([Bloomberg Real-Time Data Feed / B-PIPE](https://professional.bloomberg.com/products/data/enterprise-catalog/real-time-data-feed/)).
- **LSEG/Refinitiv Real-Time** (formerly Elektron/RTDS/TREP) is the equivalent enterprise feed + in-house distribution system, with proximity/colo hosting options ([LSEG data feeds](https://www.lseg.com/en/data-analytics/market-data/data-feeds)).
- **ICE Consolidated Feed** normalizes 600+ sources / 300+ exchanges / 25M+ instruments with L1 and full L2 order book across asset classes ([ICE Consolidated Feed](https://www.ice.com/fixed-income-data-services/access-and-delivery/connectivity-and-feeds/consolidated-feed)).

**The load-bearing insight:** *Bloomberg itself sells a normalized feed, not the raw exchange firehose.* "The way Bloomberg does it" already means **Layer 3**. Going to Layer 1 is for latency-sensitive trading, not for research/backtest/paper platforms.

### 1.4 What "direct from the exchange" actually requires

It is an operational build, not a subscription:
- **Co-location cage/rack** in the exchange data center (Equinix NY4/NY5 Secaucus, NYSE Mahwah, Nasdaq Carteret), with power and space — or rent a **hosted ticker-plant** ([Exegy Hosted Ticker Plant](https://www.exegy.com/products/hosted-ticker-plant/)).
- **Cross-connects / 10–100 GbE handoff** to receive the exchange's multicast UDP groups (A/B lines).
- **Feed handler / ticker plant software** per venue: join multicast, decode the binary protocol, do A/B line arbitration, build/maintain the order book, handle sequence-gap detection + retransmission, and **normalize** into one schema + symbology. Vendors: **Exegy** (merged with Vela; SMDS/nxFeed/XTP, FPGA), **Pico/Redline** (InRush ticker plant), **NovaSparks** (pure FPGA, sub-µs), **OnixS** (build-your-own SDKs), **Enyx** (FPGA cards) ([Exegy Ticker Plant](https://www.exegy.com/products/exegy-ticker-plant/), [Pico InRush](https://www.pico.net/redline-software/inrush-ticker-plant/), [NovaSparks](https://novasparks.com/novasparks-is-voted-best-high-performance-data-feed-handler/)).
- **FPGA acceleration** for the lowest tier (sub-µs / nanosecond decode), plus **microwave transport** (McKay Brothers/Quincy) between venues.
- **Per-exchange data-license fees** on top of all of it (§2).

This is the Bloomberg/Citadel-grade build. **Ithaca does not need any of it.** The endgame for Ithaca (if it ever arrives) is at most a *normalized direct-feed vendor* (Databento), not a self-operated colo ticker plant.

---

## 2. The licensing & cost reality (the part founders underestimate)

Exchange fee schedules are assembled from stacked components — you almost never pay just one:

| Component | Charges for | Unit |
|---|---|---|
| **Access fee** | The right to receive the feed at all | flat $/mo per product |
| **Per-user / per-device** | Each human who *views* the data (display) | $/user/mo, split Pro vs Non-Pro |
| **Non-display fee** | Any *machine/automated* consumption | flat $/mo per category, per product |
| **Redistribution fee** | The right to pass data to external parties | flat $/mo |
| **Enterprise license** | Buy-out of per-user counting | large flat $/mo or annual |

Source: [Exegy — Market Data Fees: planning infrastructure](https://www.exegy.com/market-data-fees-planning-infrastructure/).

### 2.1 Concrete published figures

**Nasdaq** (US Equities Price List 2025–2027) ([PDF](https://www.nasdaqtrader.com/content/ProductsServices/PriceList/Nasdaq_US_Equities_Price_List_2025_2026_2027.pdf)):
- TotalView display: **Professional $80.50/user/mo** vs **Non-Professional $15.00/user/mo** (2025).
- TotalView **Non-Display**, per firm/mo, tiered: 40–99 subs **$15,840**; 100–249 **$31,680**; **250+ $75,000**.
- TotalView Enterprise License **$25,000/mo** + depth subscriber fees; Non-Display Enterprise (Direct Access) **$75,000/mo**.

**NYSE** (Proprietary Market Data Fee Schedule, as of 2026-03-16) ([PDF](https://www.nyse.com/publicdocs/nyse/data/NYSE_Market_Data_Fee_Schedule.pdf)):
- Integrated Feed: Access **$8,400/mo**; Pro user **$78/mo**; Non-Pro **$16/mo**; **Non-Display $22,400/mo per category** (cap $67,200); Redistribution **$4,400/mo**.
- So NYSE Integrated alone, one non-display category + redistribution = **~$35,200/mo (~$422k/yr)** before any per-user fees — *for one exchange's feed*.

### 2.2 Professional vs Non-Professional (an order-of-magnitude lever)

The gap is ~5x on depth feeds (Nasdaq $80.50 vs $15.00; NYSE $78 vs $16) and up to 27x on Nasdaq Basic. To qualify as **Non-Professional** you must be a *natural person*, use the data *only for personal use*, *not be registered/qualified* with any securities regulator, *not be an investment adviser*, and *trade only your own capital* ([Interactive Brokers definitions](https://www.interactivebrokers.com/en/accounts/fees/professionalDefinations.php), [NYSE Non-Professional Subscriber Policy](https://www.nyse.com/publicdocs/nyse/data/Policy-Non-ProfessionalSubscribers_PDP.pdf)). **For a B2B/agent platform, assume essentially every user is Professional** — and assume audits will reclassify aggressively ("professional-user creep").

### 2.3 Non-display use — the dominant cost for an AI-agent platform

**Non-display = any use that does not put the data on a screen for a human.** This explicitly includes algorithmic trading, automated decision systems, analytics pipelines — and **feeding quotes to an AI agent or model.** If a machine "reads" the quote, it is non-display, charged as a **flat, large, per-firm fee** with no Non-Pro discount. NYSE's categories: **Cat 1** = on your own behalf; **Cat 2** = on behalf of clients; **Cat 3** = internal order matching ([NYSE fee schedule](https://www.nyse.com/publicdocs/nyse/data/NYSE_Market_Data_Fee_Schedule.pdf)). Nasdaq mirrors this ([Nasdaq Data Policies](https://www.nasdaqtrader.com/content/AdministrationSupport/Policy/USEquitiesandOptionsDataPolicies.pdf)).

> **This is THE gotcha for Ithaca.** A platform where external agents consume real-time quotes is, by definition, **non-display, Category 2 (on behalf of clients)** use. If Ithaca held the exchange feeds directly, it would owe the firmwide non-display fee for *every exchange feed its agents touch* — independent of having 10 customers or 10,000. That is the line that turns "we have a handful of pilot users" into "$400k+/yr in data fees." **The architecture must route this through a vendor that already holds those licenses, and lean on the derived-data path (§2.5) and EOD/PIT data wherever possible.**

The SIP non-display equivalent runs ~$9,500/mo per system per tape on top of proprietary feeds ([Intrinio — NYSE/CTA tapes](https://intrinio.com/blog/understanding-nyse-cta-tapes-a-b-and-c)).

### 2.4 Redistribution — what you must do to serve data downstream

If you serve exchange data to customers (even normalized, even via API) you are a **redistributor** and need a vendor/distributor agreement on top of data fees. Obligations: sign each plan/exchange vendor agreement and pay redistribution fees; **operate an entitlement system** classifying each recipient Pro/Non-Pro and **retain entitlement reports ≥3 years post-termination**; **report subscriber counts monthly**; **file the annual Non-Display Use Declaration by Jan 31** (else $1,000/mo/product late fee); and **submit to audits** ([Nasdaq UTP Vendor Agreement](https://www.utpplan.com/DOC/VendorAgreement.pdf), [NYSE Market Data Vendor Guide](https://www.nyse.com/publicdocs/ctaplan/notifications/trader-update/NYSE%20Market%20Data%20Vendor%20Guide.pdf)). **Delayed (15-min) and EOD data carry far lighter obligations** — a key escape hatch.

### 2.5 Derived data — when computed outputs escape per-quote licensing

"Derived data" = new works computed from raw data that **cannot be reverse-engineered back into, and are not substantially similar to, the original** — a signal value, a volatility surface, a backtest equity curve, a buy/sell conclusion, an aggregated statistic ([Markets Media — Complexities in Market Data Licensing](https://www.marketsmedia.com/complexities-expand-in-market-data-licensing/)). Genuinely derived output may escape per-quote *display/redistribution* licensing. **Catches:** (a) computing it still requires a **non-display license on the input**; (b) exchanges increasingly require a specific derived-data license (Nasdaq lists a Non-Professional Derived Data License at $1,500/firm/mo); (c) "derived enough" is judged after the fact in audits.

> **Strategic fit:** Ithaca's product is *literally* a derived-data engine — agents receive signals, factor scores, backtest curves, risk decompositions, **not raw redistributed quotes.** The provenance/`panelType` contract already serves computed conclusions. This is the legitimate path to minimize output licensing. We still pay the *input* non-display license — which is exactly why we buy it from a vendor.

### 2.6 Realistic annual cost tiers

| Path | Realistic annual cost |
|---|---|
| Vendor API, internal/display-only, small | **$2k–$10k** |
| Vendor API, redistribution + some non-display (agent consumption) | **~$30k–$150k** |
| Direct proprietary depth feeds + non-display + redistribution + colo (full US equities) | **~$1M–$2M+** |

The direct-feed figure is grounded: Exegy's worked example totals ~$111,020/mo (~$1.3M/yr) in **exchange data fees alone** for full US equity depth feeds with one non-display category + redistribution, before colo/FPGA/connectivity (commonly another $100k–$500k+/yr) ([Exegy](https://www.exegy.com/market-data-fees-planning-infrastructure/)).

### 2.7 The friction founders underestimate

1. **Audits are routine, not hypothetical** — exchanges audit the **3 prior years** of entitlement records, MISU firms annually at their own expense ([CTA MISU Policy](https://www.nyse.com/publicdocs/nyse/data/MISU_Policy_with_FAQ.pdf)).
2. **"You owe back-fees"** — underreporting triggers retroactive liability + interest (Nasdaq UTP: pay within 15 days of discovery); a 3-year window + a misclassification = six-figure surprise invoice.
3. **You pay the auditor** if a shortfall ≥~10% / material breach is found (CME, ICE).
4. **Continuous reporting burden** — monthly counts, 3-year retention, annual non-display declaration.
5. **Derived-data ambiguity** is decided by the exchange in an audit, not by you at design time — document derivation logic.

---

## 3. The realistic vendor menu for a startup

> Sourcing caveat: several pricing pages are JS-rendered or login-gated; dollar figures are from vendor blog/announcement posts, docs, and recent third-party reviews, flagged where a single source couldn't be cross-confirmed. **Polygon.io rebranded to "Massive" (massive.com) on 2025-10-30**; `api.polygon.io` still works ([massive.com/blog/polygon-is-now-massive](https://massive.com/blog/polygon-is-now-massive)). **CRSP was acquired by Morningstar (~$365M, announced Sept 2025, completed ~Feb 2026)** — a continuity flag ([Wikipedia — CRSP](https://en.wikipedia.org/wiki/Center_for_Research_in_Security_Prices)).

### Tier A — Direct-feed / consolidated real-time vendors

**Databento** — genuine **direct exchange feeds captured in colocation**: NYSE/Arca/Amex via **Pillar**, Nasdaq venues via **TotalView-ITCH**, cross-connects in NY4 + CME Aurora ([introducing-databento-us-equities](https://databento.com/blog/introducing-databento-us-equities), [CME vendor page](https://www.cmegroup.com/solutions/market-tech-and-data-services/technology-vendor-services/databento.html)). Unified live + historical API, one normalized schema (DBN), Python/C++/Rust clients, L2/L3 order book. **PIT-grade extras:** a **Security Master** with PIT historical identifiers/status, 18 yrs, listed + delisted (survivorship-free) ([databento.com/security-master](https://databento.com/security-master)); a **Corporate Actions** product (~6 yrs PIT, 215 exchanges, 60+ event types) ([corporate-actions](https://databento.com/blog/corporate-actions)). **Pricing:** historical is **pay-as-you-go**; live moved to subscription Jan 2025, **Standard ~$199/mo** + enterprise tiers ([Jan 2025 pricing](https://databento.com/blog/upcoming-changes-to-pricing-plans-in-january-2025)). **Good at:** real protocols, order-book depth, PIT security master + corp actions, best-in-class DX, pay-as-you-go history. **Bad at:** no fundamentals/estimates; corp-action history only ~6 yr; live needs a subscription.

**Polygon.io / Massive** — **SIP-consolidated** (CTA+UTP), *not* direct ITCH/Pillar colo. REST + WebSocket + **bulk flat files** (S3 history). Ticker-centric "PIT-by-ticker," served to delisting date, but reviewers flag data-quality gaps (dividends, missing/dup trades, delisted metadata) ([review](https://medium.com/@yolotrading/a-complete-review-of-the-polygon-io-api-everything-you-wanted-to-know-c79e992a74ff)). **Pricing (per asset class):** Free $0; Stocks ~Starter $29 / Developer $79 / **Advanced ~$199** ([roundup](https://www.mexc.com/news/476023)). **Good at:** low cost, fast/stable API, WebSocket, flat files, easy onboarding. **Bad at:** SIP-only (no direct-feed depth), data-quality concerns, no fundamentals/PIT, per-asset-class billing.

**ICE Data Services — Consolidated Feed** — enterprise normalized feed, 600+ sources / 300+ exchanges / 25M+ instruments, L1/L2/L3 all asset classes, evaluated bond pricing, 10+ yr tick history ([Consolidated Feed](https://www.ice.com/fixed-income-data-services/access-and-delivery/connectivity-and-feeds/consolidated-feed)). **Enterprise/contract-only**, opaque pricing. **Good at:** breadth, full book, deep history, reliability. **Bad at:** no self-serve, overkill for a startup.

**LSEG / Refinitiv** — Real-Time (cloud + RTDS on-prem) and **Real-Time Direct/Ultra Direct** for true direct feeds; **Tick History (TRTH)** to **Jan 1996** incl. **PCAP** with GPS-nanosecond timestamps "sourced directly from exchanges" ([tick-history](https://www.lseg.com/en/data-analytics/market-data/data-feeds/tick-history)); fundamentals via Datastream/Worldscope; proprietary **RIC** symbology. PIT fundamentals exist but are a **paid add-on, not the default**. **Enterprise/quote-only**, six-figure+. **Good at:** deepest tick history + genuine direct PCAP, global breadth. **Bad at:** procurement friction, RIC lock-in, PIT fundamentals must be stitched together.

### Tier B — Affordable API-first feeds (operational live + recent history)

**Intrinio** — real-time/delayed/EOD + 50yr history; options; **both as-reported and standardized SEC fundamentals**. Mixed sources (own EquitiesEdge, IEX, Nasdaq Basic, 15-min SIP; full depth behind Enterprise). Not a rigorously versioned PIT panel. **Pricing:** Individual $150/mo (non-commercial), Startup ~$333→$999/mo, Enterprise from $1,250/mo ([pricing](https://intrinio.com/pricing)). **Good at:** clean API, as-reported SEC fundamentals. **Bad at:** not a survivorship-free research panel; cheap tiers are partial-market.

**Tiingo** — EOD for 65k+ securities, IEX real-time, **news API**, thin third-party fundamentals; includes delisted tickers but **not validated as academically survivorship-bias-free** (no delisting returns, no historical index constituents). **Pricing:** Free; **Power User $10/mo**; commercial/redistribution ~$250–$500 ([pricing](https://www.tiingo.com/about/pricing)). **Good at:** unbeatable price-to-coverage, news. **Bad at:** not bias-free academically, thin fundamentals, single-exchange (IEX) real-time.

**Alpaca** — commission-free **broker + market-data API** (equities/options/crypto). **CTA/UTP** consolidated tape + **OPRA**. **Free = IEX-only; full SIP requires paid.** **Basic $0** (IEX, 15-min delayed REST); **Algo Trader Plus $99/mo** (full SIP real-time, OPRA, corporate actions, 10,000 calls/min) ([data-faq](https://docs.alpaca.markets/us/docs/market-data-faq)). History ~2016+. **Good at:** transparent cheap pricing, unified broker+data+execution (a natural fit for the §5.6 `ExecutionVenue` seam when paper→live ever happens), modern API. **Bad at:** no fundamentals/PIT, no survivorship framework, ~2016+ history, free IEX feed thin.

**dxFeed** — managed ticker plant with **direct market data feeds** from worldwide exchanges; strong **options** (full OPRA + Greeks/IV) ([choose.dxfeed.com](https://choose.dxfeed.com/), [options](https://dxfeed.com/market-data/options/)). Quote-based pricing (retail from ~$19/mo; enterprise indicative ~$350/mo). **Good at:** direct real-time + historical tick/options, full OPRA + Greeks. **Bad at:** no fundamentals/PIT, opaque pricing, OPRA entitlement overhead.

### Tier C — Honest-backtesting research datasets (the ones that matter most)

These are the datasets that genuinely unblock the cut-list item. **The first three bake bias-free/PIT into their core product**; FactSet/LSEG only unblock it if you specifically procure the PIT add-on.

**Sharadar (Core US Fundamentals SF1 / Core US Equities SEP)** — the honest-backtesting workhorse for a startup budget. Derived from SEC filings (EOD/batch, **not** a direct feed). **The PIT mechanics are explicit and exactly what §2.4 needs:** SF1 carries **`DATEKEY`** (actual SEC filing date = when the data became knowable), `REPORTPERIOD`, `CALENDARDATE`, `LASTUPDATED`; dimensions encode **`AR` = As Reported (true vintage)** vs **`MR` = Most Recent (restated)**, crossed with Q/Y/T → ARQ/ARY/ART/MRQ/MRY/MRT ([SF1](https://data.nasdaq.com/databases/SF1)). Coverage: 16,000+ companies (~6,000 active + ~10,000 delisted), fundamentals since 1990, SEP prices since 1998 across 21,000+ active/delisted tickers, "nearly completely free from survivorship bias" ([SEP](https://data.nasdaq.com/databases/SEP)). Distributed direct at sharadar.com **and via Nasdaq Data Link**. Pricing is license-gated (Personal/Academic/Business), historically low-tens-to-low-hundreds-of-$/mo for personal — **verify live**. **Good at:** the cheapest credible honest-backtesting path — true PIT, AR/MR vintage toggle, delisted coverage, adjusted EOD prices, decades of history, simple API. **Bad at:** EOD only (no intraday/options), US-equity-centric, reseller SLA, shorter history than CRSP.

**CRSP** — the academic gold standard: **survivorship-bias-free with explicit delisting returns** (the single most important detail for honest long-horizon backtests). US daily/monthly since **1926** (NYSE), plus the Survivor-Bias-Free Mutual Fund DB; PIT fundamentals via **CRSP/Compustat Merged (CCM)** ([WRDS CRSP](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/center-for-research-in-security-prices-crsp/)). Access almost always via **WRDS** institutional subscription (academic); commercial is a pricier negotiated license. **Good at:** the gold standard. **Bad at:** no real-time, WRDS-gated, opaque high cost, PIT requires researcher discipline, recent Morningstar-ownership uncertainty.

**Norgate Data** — affordable **survivorship-bias-free EOD** purpose-built for backtesting; includes delisted stocks **and historically accurate index constituents** (eliminates both survivorship *and* index-membership look-ahead — rare). US bias-free back to 1950 (Diamond) / 1990 (Platinum). **Pricing (US, 12-mo):** Silver $270, Gold $360, **Platinum $630** (delisted + historical constituents → 1990, the minimum honest tier), Diamond $787.50 ([packages](https://norgatedata.com/stockmarketpackages.php)). Plugin model (AmiBroker/Python/Zipline), **not generic REST**. **Good at:** affordable genuine bias-free EOD + historical index constituents; deep US futures. **Bad at:** EOD only, weak PIT fundamentals, plugin model.

**FactSet** — **Fundamentals Point-in-Time** (as-reported, vintage/as-of dates since **Feb 1999**) + best-in-class **Symbology/Entity Master** preserving historical identifier mappings so delisted/changed securities resolve correctly ([PIT product](https://www.factset.com/marketplace/catalog/product/factset-fundamentals-point-in-time)); consolidated real-time via Exchange DataFeed. Enterprise/quote-only, five-to-six-figure+. **Good at:** best symbology/entity-linking, genuine PIT vintaged fundamentals. **Bad at:** enterprise cost; PIT only to 1999.

**Nasdaq Data Link (formerly Quandl)** — a **marketplace/distribution platform** (time-series + datatables API, R/Python/Excel), not primarily a producer; **no direct feeds**. Matters here because it **hosts the Sharadar datasets** (SF1/SEP/SFA) — the easiest single API to consume Sharadar ([SHARADAR publisher](https://data.nasdaq.com/publishers/SHARADAR)). **Good at:** cheapest credible PIT path (via Sharadar), clean API. **Bad at:** US-centric, EOD only, reseller SLA.

### 3.1 Which vendors take direct exchange feeds?

| Vendor | Direct exchange feeds? | PIT / survivorship-free history? |
|---|---|---|
| Databento | **Yes** (ITCH + Pillar, colo) | Security Master (PIT IDs, delisted) + Corp Actions; no fundamentals |
| Polygon/Massive | No (SIP-consolidated) | PIT-by-ticker only; quality caveats |
| ICE Consolidated Feed | Normalized (aggregates direct sources) | reference/PIT at contract level |
| LSEG/Refinitiv | **Yes** (Real-Time Direct/PCAP) | yes, but **paid add-on** (Worldscope/Datastream PIT) |
| FactSet | Consolidated | **Yes** — PIT fundamentals 1999+, historical symbology |
| Nasdaq Data Link | No (marketplace) | via **Sharadar** |
| Intrinio | Mixed (IEX, Nasdaq Basic, SIP) | as-reported, not versioned PIT |
| Tiingo | IEX (one exchange) | delisted included, not academically bias-free |
| CRSP | n/a (research DB) | **Yes** — gold standard, delisting returns, 1926+ |
| Norgate | n/a (EOD research) | **Yes** — bias-free + historical index constituents |
| Sharadar | No (SEC-derived EOD) | **Yes** — DATEKEY vintages, AR/MR, delisted |
| dxFeed | **Yes** (direct, options strong) | tick replay; no fundamentals |
| Alpaca | No (SIP + OPRA) | no PIT/survivorship framework |

---

## 4. What this unlocks for the product

The decision to buy official data lifts specific constraints the plan currently bakes in:

1. **Fundamental-factor backtesting comes OFF the cut list.** §2.4's `[CUT-FOR-v2.0]` ("Fundamental-factor backtests are forbidden at launch") and §5.1's primitives-only framing for factor strategies were forced *entirely* by the lack of a vintaged source. **Sharadar SF1 supplies exactly the missing ingredient: as-reported fundamentals with `DATEKEY` vintages and AR/MR dimensions.** With it wired, the worker path's `asOf = bar_i` truncation becomes *real* against fundamentals, not estimated. The §2.4 sentence "Fundamental-factor backtesting unlocks only when a vintaged source (Sharadar/Compustat PIT) is wired" is now satisfiable at launch budget.

2. **Survivorship bias is eliminated, full-universe becomes honest.** Sharadar (delisted included), Norgate (delisted + historical index constituents), and CRSP (delisting returns) all carry delisted securities and point-in-time membership. The `screen.universe` tool's "(PIT-aware via `listedAt`)" promise (§4.1) and the §10 risk #1 ("Free sources can't deliver true PIT") are directly addressed. Cross-sectional rank strategies stop silently selecting only survivors.

3. **`pit: true` becomes legitimately attainable per source.** The provenance `pit` flag (§2.4, §4.2) was destined to read `false`/`estimated` for everything fundamental under Yahoo. Now: Sharadar fundamentals → `pit: true`; Databento Security Master + corp actions → `pit: true` for prices/identifiers; EDGAR/news already `pit: true`. The flag stops being an apology and becomes a real capability signal.

4. **Real intraday and order-book data become real.** Databento's direct ITCH/Pillar feeds make `market.get_intraday` and `market.get_trade_flow` (§4.1) genuinely exchange-grade, and resurrect a *bounded* path for `market.reconstruct_order_book` (the IEX-DEEP tool cut in §4.1 for decoding ~13GB) — Databento serves normalized L2/L3 directly, removing the in-process decode that motivated the cut (though the async/byte-cap discipline from §4.1 still applies).

5. **Honest backtest diagnostics gain teeth.** Flow 3's "always emit walk-forward/overfitting diagnostics (deflated Sharpe, PBO/CSCV)" (§3) is only meaningful on a survivorship-free, point-in-time universe. With Yahoo, those diagnostics decorated a biased sample; with PIT data they measure something true.

6. **Corporate-actions correctness.** Databento corporate actions + Sharadar's adjusted/unadjusted views replace Yahoo's silently-restated dividend/split series — removing a whole class of backtest distortion the plan called out as "dividend-restated."

**What does NOT change / stays cut:** microsecond latency, colo, FPGA — irrelevant to research + paper-live. Ithaca never needs Layer-1 latency. `deploy:live` stays unissuable (§5.6); the freshness floor on paper-live (§7) still governs the money path regardless of source quality.

---

## 5. Recommendation + phased path

### 5.1 The pragmatic answer

**Buy "official quality" by buying from vendors that themselves take direct exchange feeds and that bake PIT into their datasets — do NOT build a colo ticker plant.** The endgame "direct feeds + colo" is a graduation state Ithaca may never need, because its product is *research + paper-trading + derived data*, not latency-sensitive execution.

The recommended launch stack — three vendors, three jobs:

| Vendor | Job | Why | Rough cost |
|---|---|---|---|
| **Sharadar SF1 + SEP** (via Nasdaq Data Link or direct) | **PIT fundamentals + survivorship-free EOD** — the honest-backtest engine | DATEKEY vintages + AR/MR dimensions + delisted; cheapest credible PIT. **This is the purchase that lifts the §2.4 cut.** | low-hundreds $/mo (business license higher; **verify quote**) |
| **Databento** | **Direct-feed prices, intraday, order book, corp actions, security master** | Real ITCH/Pillar in colo; pay-as-you-go history; PIT security master. Makes `market.*` exchange-grade. | history pay-as-you-go (~$100s/mo typical); live Standard ~$199/mo |
| **Alpaca Algo Trader Plus** | **Broker-grade SIP real-time for paper-live ticks** + the natural future `ExecutionVenue` | Full SIP + OPRA + corporate actions at $99/mo; one provider for data + (future) execution; satisfies the §7 freshness floor on the money path | $99/mo |

Add **Tiingo Power User ($10/mo)** as a cheap news + redundancy source for `news.*`, and keep **EDGAR/FRED/Polymarket** as the already-PIT free sources for `ownership.*`/`macro.*`. **CRSP (via WRDS)** and **Norgate Platinum** are *optional later additions* for academic-grade validation / historical-index-constituent rigor, not launch dependencies.

### 5.2 Phased path (slots into the plan's roadmap)

- **Phase 0.5(b) — the honest-backtest spike (already in the plan).** Procure **Sharadar SF1+SEP**, produce the "one defensibly-PIT backtest" the spike demands — now a *fundamental-factor* one, not just price. Enumerate exactly which sources support `pit: true`. **Cost: ~$1–3k for the spike period.**
- **Phase 1 — Data Layer walking skeleton.** Wire **Databento** behind `sources/prices` for `market.get_ohlcv` (direct-feed daily/intraday) and **Sharadar** behind `sources/fundamentals` for `fundamentals.get_history` with real `asOf` truncation. Both expose the per-source `pit` flag honestly. **Cost: ~$300–700/mo.**
- **Phase 3 — Backtest on DO.** The backtest worker pulls a PIT bulk window from Databento (prices) + Sharadar (fundamentals AR dimension at `asOf = bar_i`). Fundamental-factor backtests are now *in scope*. **Cost: usage-metered Databento history + Sharadar flat.**
- **Phase 4 — Paper-live.** Wire **Alpaca Algo Trader Plus** SIP real-time behind the paper-live tick; the §7 freshness floor governs skip-and-alert. **Cost: +$99/mo.**
- **Phase 5 — Breadth + (optional) rigor.** Add Tiingo news, dxFeed if options depth is needed, and **CRSP/Norgate** if academic-grade validation or historical-index-constituent universes become a selling point. **Cost: $10–250/mo + (CRSP via WRDS, negotiated).**

**Rough cost envelope:** launch (Phases 0.5–4) lands around **$500–$1,500/mo (~$6k–$18k/yr)** of vendor spend — well inside the "Vendor API, small" tier (§2.6) and well below the non-display cliff, *because Ithaca serves derived data (§2.5) and uses EOD/PIT data for research rather than redistributing raw real-time quotes.* The "direct feeds + colo" tier ($1M+/yr) is explicitly out of scope.

### 5.3 The graduation trigger

Move from "vendor API" toward "direct feeds + colo" (or a heavier Databento/dxFeed enterprise tier) **only when**:
- Latency becomes product-load-bearing — i.e., `deploy:live` ships and real fills depend on sub-millisecond data (today `deploy:live` is unissuable, so this trigger is years out), **or**
- Vendor metered/redistribution costs cross ~$150k/yr (the point where direct-feed economics begin to compete), **or**
- A customer contract requires data Ithaca can only get under its own exchange agreement.

Until any of those fire, **stay on vendors.** The architecture makes graduation a `sources/` adapter swap, not a rewrite (§5.4).

### 5.4 How it slots into ithaca-core

This decision touches **only** the source adapter layer and the provenance flag — the §2.3/§2.4 architecture was already built for it:

- **`ithaca-core/sources/`** gains adapters: `sources/prices` → Databento; `sources/fundamentals` → Sharadar; a `sources/live` → Alpaca SIP. Each is a `_resilient`-wrapped adapter behind the same breakers/provenance builder. Swapping Yahoo→Databento is an adapter change, not a contract change.
- **The Data Gateway facade (§2.3)** is unchanged: it still applies the single `asOf` truncation knob. The difference is that `asOf` truncation against **Sharadar's `DATEKEY`/AR dimension is now truthful**, where against Yahoo it was estimated. The worker path's `asOf = bar_i` finally means what it claims.
- **The per-source `pit` capability flag (§2.4, §4.2)** is the exact seam this plugs into: each adapter declares `pit: true|false|estimated`. Sharadar fundamentals and Databento prices/corp-actions report `pit: true`; the flag stops being a forced `false`.
- **The global-upstream-cache exception (§7)** for public market data still lives in one reviewed module — now caching *licensed* vendor data, which sharpens the need for the entitlement/derived-data discipline in §2.4/§2.5.

---

## 6. Concrete changes to the master plan

Short, surgical edits given this decision:

**§2.4 (point-in-time):**
- Strike `[CUT-FOR-v2.0] Fundamental-factor backtests are forbidden at launch.` Replace with: *"Fundamental-factor backtests are IN SCOPE at launch, sourced from Sharadar SF1 (as-reported `DATEKEY` vintages, AR/MR dimensions). The `asOf` truncation is truthful against Sharadar's filing-date vintaging, not estimated."*
- Update the bullet on Yahoo's deficiencies: Yahoo is **dropped** as a source; the survivorship-bias/dividend-restatement/no-vintaging critique is resolved by the vendor stack rather than worked around.

**§4.1 (tool taxonomy):**
- `fundamentals.get_history` → annotate **PIT-capable (Sharadar SF1, vintaged)**; `fundamentals.get_snapshot` sourced from Sharadar MR dimension.
- `market.get_ohlcv` / `get_intraday` / `get_trade_flow` → note source is **Databento direct feeds (ITCH/Pillar)**, `pit: true`.
- `screen.universe` → now genuinely PIT-aware (delisted included via Sharadar/Databento Security Master), not aspirational.
- The `[CUT-FOR-v2.0]` on `market.reconstruct_order_book` can be **relaxed**: Databento serves normalized L2/L3 directly, removing the 13GB in-process decode; keep the async/byte-cap discipline but the cut rationale (IEX-DEEP decode cost) no longer applies.

**§4.2 (provenance contract):**
- Update the example `source` from `"yahoo-chart"` to a real source (e.g. `"databento-xnas-itch"` / `"sharadar-sf1"`), and show `"pit": "true"` as the realistic default for the priced/fundamental paths.
- Add a `license` field note to provenance for non-display/derived-data audit traceability (which source, which entitlement, derived vs raw).

**§4.3 (porting map):**
- The "fix-on-port" list should add: **replace the Yahoo adapter in `sources/prices` with a Databento adapter; replace `fetch_fundamentals_history`'s 45-day-lag estimation with Sharadar `DATEKEY`-driven truthful vintaging.** This removes the single worst data-honesty hack in the v1 code.

**§10 (risks):**
- Risk #1 (PIT data honesty) is **downgraded from CRITICAL/open to RESOLVED-at-launch**: the vintaged source (Sharadar) is now a launch dependency, not an open question. Replace the "Open: budget/timeline for a vintaged fundamentals source" line with the cost envelope in §5.2 of this doc.
- Add a **new MEDIUM risk: market-data licensing/audit exposure** — non-display (Category 2) treatment of agent consumption, redistribution obligations, and the 3-year back-fee audit risk (§2.3/§2.7). Mitigation: buy through vendors who hold the licenses, serve derived data not raw quotes, and keep entitlement/usage records from day one.

---

### Consolidated source list
- Nasdaq TotalView-ITCH spec — https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHSpecification.pdf
- NYSE XDP Integrated Feed Client Spec — https://www.nyse.com/publicdocs/nyse/data/Integrated_Feed_Client_Specification_v2.3d.pdf
- Cboe Multicast PITCH spec — https://www.cboe.com/document/tech-spec/document/technical-specifications/cboe-titanium-u.s.-equitiesoptions-multicast-pitch-specification
- Databento — proprietary feeds vs SIP — https://databento.com/blog/proprietary-feeds-vs-sip-data
- Databento — introducing US equities (direct feeds) — https://databento.com/blog/introducing-databento-us-equities
- Databento — Security Master — https://databento.com/security-master
- Databento — Corporate Actions — https://databento.com/blog/corporate-actions
- Databento — Jan 2025 pricing — https://databento.com/blog/upcoming-changes-to-pricing-plans-in-january-2025
- Securities Information Processor — Wikipedia — https://en.wikipedia.org/wiki/Securities_information_processor
- Sidley — D.C. Circuit upholds MDIR — https://www.sidley.com/en/insights/newsupdates/2022/06/dc-circuit-upholds-secs-market-data-infrastructure-rules-paving-the-way-for-competing-consolidators
- SIFMA — CT Plan fee filing letter (Aug 2025) — https://www.sifma.org/wp-content/uploads/2025/08/SIFMA-Letter-re-Equity-Market-Data-8.25.2025.pdf
- Traders Magazine — Competing Consolidators without CT Plan — https://www.tradersmagazine.com/am/market-data-competing-consolidators-without-ct-plan/
- Bloomberg — SIP vs Direct Feeds latency — https://www.bloomberg.com/professional/blog/sip-vs-direct-feeds-latency-rules/
- Exegy — Hosted Ticker Plant — https://www.exegy.com/products/hosted-ticker-plant/
- Exegy — Ticker Plant (XTP) — https://www.exegy.com/products/exegy-ticker-plant/
- Exegy — Market data fees & infrastructure planning — https://www.exegy.com/market-data-fees-planning-infrastructure/
- Pico InRush Ticker Plant — https://www.pico.net/redline-software/inrush-ticker-plant/
- NovaSparks FPGA feed handler — https://novasparks.com/novasparks-is-voted-best-high-performance-data-feed-handler/
- Bloomberg B-PIPE / Real-Time Data Feed — https://professional.bloomberg.com/products/data/enterprise-catalog/real-time-data-feed/
- LSEG Real-Time data feeds — https://www.lseg.com/en/data-analytics/market-data/data-feeds
- LSEG Tick History (TRTH/PCAP) — https://www.lseg.com/en/data-analytics/market-data/data-feeds/tick-history
- ICE Consolidated Feed — https://www.ice.com/fixed-income-data-services/access-and-delivery/connectivity-and-feeds/consolidated-feed
- Nasdaq US Equities Price List 2025–2027 — https://www.nasdaqtrader.com/content/ProductsServices/PriceList/Nasdaq_US_Equities_Price_List_2025_2026_2027.pdf
- NYSE Proprietary Market Data Fee Schedule — https://www.nyse.com/publicdocs/nyse/data/NYSE_Market_Data_Fee_Schedule.pdf
- Nasdaq US Equities & Options Data Policies — https://www.nasdaqtrader.com/content/AdministrationSupport/Policy/USEquitiesandOptionsDataPolicies.pdf
- NYSE Non-Professional Subscriber Policy — https://www.nyse.com/publicdocs/nyse/data/Policy-Non-ProfessionalSubscribers_PDP.pdf
- Interactive Brokers — Pro/Non-Pro definitions — https://www.interactivebrokers.com/en/accounts/fees/professionalDefinations.php
- Nasdaq UTP Plan Vendor Agreement — https://www.utpplan.com/DOC/VendorAgreement.pdf
- NYSE Market Data Vendor Guide — https://www.nyse.com/publicdocs/ctaplan/notifications/trader-update/NYSE%20Market%20Data%20Vendor%20Guide.pdf
- CTA MISU Policy — https://www.nyse.com/publicdocs/nyse/data/MISU_Policy_with_FAQ.pdf
- Markets Media — Complexities Expand in Market Data Licensing — https://www.marketsmedia.com/complexities-expand-in-market-data-licensing/
- Polygon → Massive rebrand — https://massive.com/blog/polygon-is-now-massive
- Polygon/Massive API review — https://medium.com/@yolotrading/a-complete-review-of-the-polygon-io-api-everything-you-wanted-to-know-c79e992a74ff
- Intrinio pricing — https://intrinio.com/pricing
- Tiingo pricing — https://www.tiingo.com/about/pricing
- Alpaca market-data FAQ — https://docs.alpaca.markets/us/docs/market-data-faq
- dxFeed — https://choose.dxfeed.com/
- Sharadar SF1 (Nasdaq Data Link) — https://data.nasdaq.com/databases/SF1
- Sharadar SEP (Nasdaq Data Link) — https://data.nasdaq.com/databases/SEP
- WRDS — CRSP — https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/center-for-research-in-security-prices-crsp/
- CRSP — Wikipedia (Morningstar acquisition) — https://en.wikipedia.org/wiki/Center_for_Research_in_Security_Prices
- Norgate Data packages — https://norgatedata.com/stockmarketpackages.php
- FactSet Fundamentals Point-in-Time — https://www.factset.com/marketplace/catalog/product/factset-fundamentals-point-in-time
