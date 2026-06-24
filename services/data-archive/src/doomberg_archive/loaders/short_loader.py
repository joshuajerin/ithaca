"""Download FINRA REGSHO short interest / volume and SEC FTD data."""
from datetime import datetime, timezone

FINRA_SHORT_URL = "https://api.finra.org/data/group/OTCMarket/name/otcShortInterest"
# Note: FINRA's actual bulk short data requires registration. Use yfinance as primary.

def fetch_short_interest_yf(symbols: list[str]) -> list[dict]:
    """Fetch short interest from Yahoo Finance for a list of symbols."""
    import yfinance as yf
    rows = []
    for sym in symbols:
        try:
            info = yf.Ticker(sym).info
            rows.append({
                "symbol": sym.upper(),
                "short_interest_shares": info.get("sharesShort"),
                "float_shares": info.get("floatShares"),
                "short_float_pct": info.get("shortPercentOfFloat", 0) * 100 if info.get("shortPercentOfFloat") else None,
                "days_to_cover": info.get("shortRatio"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            continue
    return rows

def fetch_sec_ftd(symbol: str) -> list[dict]:
    """Fetch failures-to-deliver from SEC (quarterly CSV files)."""
    # SEC FTD files: https://www.sec.gov/data/foiadocuments/series-and-class-data
    # Most recent quarter file
    rows = []
    try:
        # For now return empty - real implementation would download and parse
        pass
    except Exception:
        pass
    return rows
