# Live market data API

Real-time, **keyless** market data served by the Vercel serverless function
(`api/[...path].js`). Backed by Yahoo Finance public endpoints (v8 chart + v1
search). Every value returned is the genuine upstream number — nothing is
synthesised. Upstream failures surface as a clean error entry, never a fake
price.

Available on both tenants:
- `https://doomberg.me/api/market/*`
- `https://kural.website/api/market/*`

All responses are JSON with permissive CORS (`Access-Control-Allow-Origin: *`)
and short edge caching (`s-maxage`), so they are callable directly from a
browser, `curl`, or any agent.

## Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/market/quote?symbols=AAPL,NVDA` | Real-time-ish quote(s). `symbols` (or `symbol`) is comma-separated, max 25. |
| GET | `/api/market/history?symbol=AAPL&range=6mo&interval=1d` | OHLCV history. `range` e.g. `1d,5d,1mo,6mo,1y,5y`; `interval` e.g. `1m,5m,1h,1d,1wk`. |
| GET | `/api/market/news?q=AAPL&limit=10` | Fresh news headlines for a ticker or topic. |
| GET | `/api/market/search?q=apple` | Symbol lookup by name/ticker. |
| GET | `/api/market/movers?limit=10` | Top gainers/losers. Optional `symbols=` to score a custom universe; defaults to a liquid large-cap set. |

`GET /api/healthz` advertises the live-data source and endpoint list.

## Examples

```bash
# Single quote
curl 'https://doomberg.me/api/market/quote?symbols=AAPL'

# Multi quote
curl 'https://doomberg.me/api/market/quote?symbols=AAPL,NVDA,MSFT'

# 6-month daily history
curl 'https://doomberg.me/api/market/history?symbol=NVDA&range=6mo&interval=1d'

# Intraday (5-minute bars, last 5 days)
curl 'https://doomberg.me/api/market/history?symbol=TSLA&range=5d&interval=5m'

# News
curl 'https://doomberg.me/api/market/news?q=NVDA&limit=5'

# Symbol search
curl 'https://doomberg.me/api/market/search?q=tesla'

# Movers across the default universe
curl 'https://doomberg.me/api/market/movers?limit=5'
```

## Response shapes

`quote`:
```json
{
  "asOf": "2026-06-18T...Z",
  "count": 1,
  "quotes": [{
    "symbol": "AAPL", "name": "Apple Inc.", "price": 295.95,
    "change": -1.23, "changePct": -0.41, "currency": "USD",
    "marketState": "REGULAR", "exchange": "NasdaqGS",
    "dayHigh": 298.1, "dayLow": 294.9, "open": 297.0,
    "previousClose": 297.18, "week52High": 317.4, "week52Low": 195.07,
    "volume": 34483000, "asOf": "2026-06-18T...Z"
  }],
  "errors": []
}
```

`history`: `{ symbol, name, currency, range, interval, price, asOf, count, points: [{ t, o, h, l, c, v }] }`

`news`: `{ query, count, news: [{ uuid, title, publisher, link, publishedAt, relatedTickers, thumbnail }] }`

## Testing

```bash
node scripts/test_live_data.mjs
```

Imports the real handler and drives every endpoint against live Yahoo upstreams.
Exits non-zero on any failure.
