---
name: Live Treasury + credit-spread sources for Fixed Income panels
description: Where the FI builders (yield curve, bond RV, CDS, cashflow/duration) get live rates/credit and the env quirks behind the choices.
---

The four Fixed Income builders pull live data via `app/sources/rates.py`:

- **US Treasury par yields:** KEY-LESS CSV at
  `https://home.treasury.gov/.../daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve`.
  Fetch current + prior 2 calendar years to populate the ago1y/ago2y comparison rows.
  Columns are `"1 Mo"`,`"3 Mo"`,`"6 Mo"`,`"1 Yr"`...`"30 Yr"` (no 4M/1.5M tenors).
- **Credit spreads (corporate OAS, used for bond RV + CDS proxy):** ICE BofA OAS
  indices via the **official FRED API** `api.stlouisfed.org` — needs a free `FRED_API_KEY`.
  Series return values in **percent → multiply by 100 for bps**. Buckets: AAA/AA/A/BBB/BB/B/CCC + IG/HY.

**Env quirk (cost real time to discover):** FRED's key-less `fredgraph.csv`/`/data` download
hosts are BLOCKED from this environment (HTTP/2 INTERNAL_ERROR / timeout), but the
keyed API host `api.stlouisfed.org` IS reachable. So credit data REQUIRES the key here even
though FRED nominally offers key-less CSV elsewhere.

**Fallback philosophy:** Treasury works with no key (yield curve + UST cashflows are live
unconditionally). Without `FRED_API_KEY`, credit-dependent panels (bond_rv, cds_pricer,
non-UST cashflow) cleanly fall back to curated mock and label `source:"mock"`. Builders
re-base mock OAS/zSpread/ASW onto the live bucket curve while preserving each name's
idiosyncratic offset, then recompute yields off the live Treasury curve.

**Refresh interval:** `RATES_REFRESH_SECONDS` env (default 3600) via `cache.cached`.
