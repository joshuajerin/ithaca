"""Macro/forex/crypto extended skills.

Provides live market data skills that reach outside the v1 archive to public
free APIs (yfinance, CoinGecko, FRED) and degrade gracefully when those feeds
are unavailable.  The envelope/provenance contract is identical to the rest of
the skill catalog.

Import pattern (mirrors extended_skills.py):
    from .macro_extended import MacroExtendedSkills
    MACRO_EXTENDED_SKILLS = {...}  # dot-name -> method_name
"""
from __future__ import annotations

import requests
from calendar import monthrange
from datetime import datetime, timezone, timedelta, date
from typing import Any

from .archive import ArchiveGateway
from .envelope import ARCHIVE_UNAVAILABLE, computed_envelope, freshness_of, warn

__all__ = ["MacroExtendedSkills", "MACRO_EXTENDED_SKILLS"]

ARCHIVE_INPUTS = "ithaca-v1-archive"

# Fetch timeout for all external HTTP calls (seconds).
_HTTP_TIMEOUT = 10

# ---------------------------------------------------------------------------
# MACRO_EXTENDED_SKILLS registry  (dot-name -> method_name)
# ---------------------------------------------------------------------------
MACRO_EXTENDED_SKILLS: dict[str, str] = {
    "macro.economic_calendar": "economic_calendar",
    "macro.fda_calendar": "fda_calendar",
    "macro.commodity_prices": "commodity_prices",
    "macro.forex_rates": "forex_rates",
    "macro.crypto_prices": "crypto_prices",
    "macro.vix_term_structure": "vix_term_structure",
    "macro.market_tide": "market_tide",
}

# ---------------------------------------------------------------------------
# Tiny typed helpers (mirrors skillset.py)
# ---------------------------------------------------------------------------

def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def _pct(new: float | None, old: float | None) -> float | None:
    """Percentage change from old to new, None-safe."""
    if new is None or old is None or old == 0:
        return None
    return round((new - old) / abs(old) * 100, 4)


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime | date) -> str:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Calendar helpers for the hardcoded economic event fallback
# ---------------------------------------------------------------------------

def _first_friday(year: int, month: int) -> date:
    """Return the first Friday of the given month."""
    d = date(year, month, 1)
    weekday = d.weekday()  # 0=Mon … 4=Fri
    delta = (4 - weekday) % 7
    return d + timedelta(days=delta)


def _last_friday(year: int, month: int) -> date:
    """Return the last Friday of the given month."""
    last_day = monthrange(year, month)[1]
    d = date(year, month, last_day)
    weekday = d.weekday()
    delta = (weekday - 4) % 7
    return d - timedelta(days=delta)


# FOMC meeting dates for 2025 / 2026 (end-date of two-day meeting).
_FOMC_2025 = [
    date(2025, 1, 29), date(2025, 3, 19), date(2025, 5, 7),
    date(2025, 6, 18), date(2025, 7, 30), date(2025, 9, 17),
    date(2025, 10, 29), date(2025, 12, 10),
]
_FOMC_2026 = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29),
    date(2026, 6, 17), date(2026, 7, 29), date(2026, 9, 16),
    date(2026, 10, 28), date(2026, 12, 9),
]
_ALL_FOMC = _FOMC_2025 + _FOMC_2026


def _build_hardcoded_calendar(days_ahead: int) -> list[dict]:
    """Return a near-term economic calendar from hard-coded rules."""
    today = date.today()
    end = today + timedelta(days=days_ahead)
    events: list[dict] = []

    # Enumerate months in range.
    months = set()
    cur = today.replace(day=1)
    while cur <= end:
        months.add((cur.year, cur.month))
        # advance by one month
        y, m = cur.year, cur.month
        m += 1
        if m > 12:
            m = 1
            y += 1
        cur = date(y, m, 1)

    for y, m in sorted(months):
        # NFP: first Friday of month
        nfp_date = _first_friday(y, m)
        if today <= nfp_date <= end:
            events.append({
                "date": _iso(nfp_date),
                "name": "Non-Farm Payrolls (NFP)",
                "importance": "high",
                "previous": None,
                "forecast": None,
                "actual": None,
            })

        # CPI: approximately the 10th
        cpi_day = min(10, monthrange(y, m)[1])
        cpi_date = date(y, m, cpi_day)
        if today <= cpi_date <= end:
            events.append({
                "date": _iso(cpi_date),
                "name": "CPI (Consumer Price Index)",
                "importance": "high",
                "previous": None,
                "forecast": None,
                "actual": None,
            })

        # PCE: last Friday of month
        pce_date = _last_friday(y, m)
        if today <= pce_date <= end:
            events.append({
                "date": _iso(pce_date),
                "name": "PCE Price Index",
                "importance": "high",
                "previous": None,
                "forecast": None,
                "actual": None,
            })

    # FOMC dates
    for fomc_date in _ALL_FOMC:
        if today <= fomc_date <= end:
            events.append({
                "date": _iso(fomc_date),
                "name": "FOMC Rate Decision",
                "importance": "high",
                "previous": None,
                "forecast": None,
                "actual": None,
            })

    events.sort(key=lambda e: e["date"])
    return events


# ---------------------------------------------------------------------------
# yfinance helper — lazy import so the rest of the module works when yfinance
# is missing; callers must catch the ImportError themselves.
# ---------------------------------------------------------------------------

def _yf():
    import yfinance as yf  # noqa: PLC0415
    return yf


def _fetch_ticker_history(symbol: str, period: str = "1mo", interval: str = "1d"):
    """Fetch yfinance history, returning an empty DataFrame on any error."""
    try:
        yf = _yf()
        t = yf.Ticker(symbol)
        hist = t.history(period=period, interval=interval, timeout=_HTTP_TIMEOUT)
        return hist
    except Exception:  # noqa: BLE001
        import pandas as pd  # noqa: PLC0415
        return pd.DataFrame()


def _change_pct(series, n_days: int) -> float | None:
    """Trailing n-day percentage change from a pandas Close series."""
    if series is None or len(series) < 2:
        return None
    tail = series.dropna()
    if len(tail) < 2:
        return None
    current = float(tail.iloc[-1])
    idx = min(n_days, len(tail) - 1)
    prior = float(tail.iloc[-1 - idx])
    return _pct(current, prior)


def _ytd_change_pct(series) -> float | None:
    """YTD percentage change from a pandas Close series."""
    if series is None or len(series) < 2:
        return None
    tail = series.dropna()
    if len(tail) < 2:
        return None
    current = float(tail.iloc[-1])
    prior = float(tail.iloc[0])
    return _pct(current, prior)


# ---------------------------------------------------------------------------
# MacroExtendedSkills
# ---------------------------------------------------------------------------

class MacroExtendedSkills:
    """Live macro/forex/crypto skills.

    Unlike the core SkillSet, some methods reach out to free public APIs
    (yfinance, CoinGecko) instead of relying solely on the v1 archive.
    Methods that need the archive check ``self.available`` and degrade.
    """

    def __init__(self, archive: ArchiveGateway | None):
        self.archive = archive
        self.available = archive is not None

    # ---- gate helpers -------------------------------------------------------

    def _computed_unavailable(self) -> dict:
        return computed_envelope(None, freshness=None, inputs=ARCHIVE_INPUTS,
                                 warnings=[dict(ARCHIVE_UNAVAILABLE)])

    def _live_envelope(self, data: Any, *, warnings: list[dict] | None = None) -> dict:
        """Envelope for skills that fetch live external data (not archive-backed)."""
        return computed_envelope(data,
                                 freshness=_now_utc().isoformat(),
                                 inputs="live-external",
                                 warnings=warnings or [])

    # =========================================================================
    # 1. economic_calendar
    # =========================================================================

    def economic_calendar(self, params: dict) -> dict:
        """Upcoming macro economic events.

        Tries to fetch a live FRED release calendar; falls back to a hardcoded
        schedule (NFP, CPI, PCE, FOMC) when FRED is unreachable.
        """
        days_ahead = _i(params.get("days_ahead"), 30, 1, 365)
        warnings: list[dict] = []

        events: list[dict] = []
        live_ok = False

        # --- attempt FRED releases endpoint ---
        try:
            end_date = (date.today() + timedelta(days=days_ahead)).isoformat()
            start_date = date.today().isoformat()
            url = (
                "https://api.stlouisfed.org/fred/releases/dates"
                f"?realtime_start={start_date}&realtime_end={end_date}"
                "&include_release_dates_with_no_data=true&file_type=json"
            )
            resp = requests.get(url, timeout=_HTTP_TIMEOUT)
            if resp.status_code == 200:
                payload = resp.json()
                release_dates = payload.get("release_dates", [])
                for rd in release_dates:
                    events.append({
                        "date": rd.get("date"),
                        "name": rd.get("release_name", "FRED Release"),
                        "importance": "medium",
                        "previous": None,
                        "forecast": None,
                        "actual": None,
                    })
                live_ok = True
        except Exception:  # noqa: BLE001
            pass

        if not live_ok:
            events = _build_hardcoded_calendar(days_ahead)
            warnings.append(warn(
                "FRED_UNAVAILABLE",
                detail="FRED API unreachable; showing hardcoded NFP/CPI/PCE/FOMC schedule",
            ))

        # deduplicate by date+name
        seen: set[tuple[str, str]] = set()
        deduped: list[dict] = []
        for e in events:
            key = (str(e.get("date", "")), str(e.get("name", "")))
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        deduped.sort(key=lambda e: str(e.get("date", "")))

        data = {
            "events": deduped,
            "count": len(deduped),
            "days_ahead": days_ahead,
            "source": "FRED" if live_ok else "hardcoded-schedule",
        }
        return self._live_envelope(data, warnings=warnings)

    # =========================================================================
    # 2. fda_calendar
    # =========================================================================

    def fda_calendar(self, params: dict) -> dict:
        """Upcoming FDA PDUFA / drug-approval decision dates.

        Attempts to fetch a live feed; returns an empty list with a note when
        no live FDA data source is reachable (public free feeds are unstable).
        """
        days_ahead = _i(params.get("days_ahead"), 90, 1, 365)
        warnings: list[dict] = []
        pdufa_dates: list[dict] = []
        live_ok = False

        # BioPharma Catalyst public JSON (best-effort, may break with site changes)
        try:
            url = "https://api.biopharmcatalyst.com/calendars/pdufa"
            resp = requests.get(url, timeout=_HTTP_TIMEOUT,
                                headers={"Accept": "application/json"})
            if resp.status_code == 200:
                items = resp.json() if isinstance(resp.json(), list) else resp.json().get("data", [])
                today = date.today()
                cutoff = today + timedelta(days=days_ahead)
                for item in items:
                    evt_date_str = item.get("date") or item.get("pdufa_date") or ""
                    try:
                        evt_date = date.fromisoformat(str(evt_date_str)[:10])
                    except ValueError:
                        continue
                    if today <= evt_date <= cutoff:
                        pdufa_dates.append({
                            "date": str(evt_date_str)[:10],
                            "drug": item.get("drug") or item.get("catalyst") or None,
                            "company": item.get("company") or item.get("ticker") or None,
                            "indication": item.get("indication") or None,
                            "decision_type": item.get("decision_type") or "PDUFA",
                        })
                live_ok = True
        except Exception:  # noqa: BLE001
            pass

        if not live_ok:
            warnings.append(warn(
                "FDA_CALENDAR_UNAVAILABLE",
                detail=(
                    "Live FDA PDUFA calendar requires a paid feed or direct FDA scraping. "
                    "No data returned. Consider integrating BioPharma Catalyst or FDA.gov directly."
                ),
            ))

        pdufa_dates.sort(key=lambda e: str(e.get("date", "")))

        data = {
            "pdufa_dates": pdufa_dates,
            "count": len(pdufa_dates),
            "days_ahead": days_ahead,
            "source": "biopharmcatalyst" if live_ok else "none",
        }
        return self._live_envelope(data, warnings=warnings)

    # =========================================================================
    # 3. commodity_prices
    # =========================================================================

    def commodity_prices(self, params: dict) -> dict:  # noqa: ARG002
        """Current prices and recent changes for major commodity futures."""
        warnings: list[dict] = []

        _COMMODITIES = [
            ("CL=F",  "Crude Oil (WTI)",  "USD/bbl"),
            ("BZ=F",  "Crude Oil (Brent)", "USD/bbl"),
            ("GC=F",  "Gold",              "USD/oz"),
            ("SI=F",  "Silver",            "USD/oz"),
            ("HG=F",  "Copper",            "USD/lb"),
            ("NG=F",  "Natural Gas",       "USD/MMBtu"),
            ("ZW=F",  "Wheat",             "USX/bu"),
            ("ZC=F",  "Corn",              "USX/bu"),
        ]

        try:
            _yf()
        except ImportError:
            warnings.append(warn("YFINANCE_MISSING",
                                 detail="yfinance not installed; cannot fetch commodity prices"))
            return self._live_envelope({"commodities": [], "count": 0}, warnings=warnings)

        commodities: list[dict] = []
        for symbol, name, unit in _COMMODITIES:
            try:
                hist = _fetch_ticker_history(symbol, period="1y", interval="1d")
                if hist.empty:
                    warnings.append(warn("COMMODITY_NO_DATA", scope=symbol,
                                         detail=f"no data returned for {symbol}"))
                    continue
                closes = hist["Close"]
                price = float(closes.iloc[-1]) if not closes.empty else None
                commodities.append({
                    "symbol": symbol,
                    "name": name,
                    "price": round(price, 4) if price is not None else None,
                    "change_1d_pct": _change_pct(closes, 1),
                    "change_1w_pct": _change_pct(closes, 5),
                    "change_1m_pct": _change_pct(closes, 21),
                    "ytd_change_pct": _ytd_change_pct(closes),
                    "unit": unit,
                    "updated_at": _now_utc().isoformat(),
                })
            except Exception as exc:  # noqa: BLE001
                warnings.append(warn("COMMODITY_FETCH_ERROR", scope=symbol,
                                     detail=str(exc)[:200]))

        data = {"commodities": commodities, "count": len(commodities)}
        return self._live_envelope(data, warnings=warnings)

    # =========================================================================
    # 4. forex_rates
    # =========================================================================

    def forex_rates(self, params: dict) -> dict:
        """Current FX rates and recent changes for major currency pairs."""
        base = str(params.get("base") or "USD").upper()
        default_pairs = [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X",
            "USDCAD=X", "USDCHF=X", "USDHKD=X",
        ]
        pairs = params.get("pairs") or default_pairs
        if isinstance(pairs, str):
            pairs = [p.strip() for p in pairs.split(",") if p.strip()]
        warnings: list[dict] = []

        try:
            _yf()
        except ImportError:
            warnings.append(warn("YFINANCE_MISSING",
                                 detail="yfinance not installed; cannot fetch FX rates"))
            return self._live_envelope({"base": base, "rates": [], "count": 0}, warnings=warnings)

        rates: list[dict] = []
        for pair in pairs:
            try:
                hist = _fetch_ticker_history(pair, period="1mo", interval="1d")
                if hist.empty:
                    warnings.append(warn("FOREX_NO_DATA", scope=pair,
                                         detail=f"no data returned for {pair}"))
                    continue
                closes = hist["Close"]
                rate = float(closes.iloc[-1]) if not closes.empty else None
                rates.append({
                    "pair": pair,
                    "rate": round(rate, 6) if rate is not None else None,
                    "change_1d_pct": _change_pct(closes, 1),
                    "change_1w_pct": _change_pct(closes, 5),
                    "updated_at": _now_utc().isoformat(),
                })
            except Exception as exc:  # noqa: BLE001
                warnings.append(warn("FOREX_FETCH_ERROR", scope=pair,
                                     detail=str(exc)[:200]))

        data = {"base": base, "rates": rates, "count": len(rates)}
        return self._live_envelope(data, warnings=warnings)

    # =========================================================================
    # 5. crypto_prices
    # =========================================================================

    def crypto_prices(self, params: dict) -> dict:
        """Current prices and market data for top cryptocurrencies via CoinGecko."""
        limit = _i(params.get("limit"), 20, 1, 250)
        warnings: list[dict] = []

        try:
            url = (
                "https://api.coingecko.com/api/v3/coins/markets"
                f"?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1"
                "&sparkline=false&price_change_percentage=24h,7d"
            )
            resp = requests.get(url, timeout=_HTTP_TIMEOUT,
                                headers={"Accept": "application/json"})
            if resp.status_code == 429:
                warnings.append(warn("COINGECKO_RATE_LIMITED",
                                     detail="CoinGecko rate limit hit; no data returned"))
                return self._live_envelope({"crypto": [], "count": 0}, warnings=warnings)
            resp.raise_for_status()
            items = resp.json()
        except requests.RequestException as exc:
            warnings.append(warn("COINGECKO_UNAVAILABLE", detail=str(exc)[:200]))
            return self._live_envelope({"crypto": [], "count": 0}, warnings=warnings)

        crypto: list[dict] = []
        for item in items:
            crypto.append({
                "symbol": str(item.get("symbol", "")).upper(),
                "name": item.get("name"),
                "price": _f(item.get("current_price")),
                "market_cap": _f(item.get("market_cap")),
                "change_24h_pct": _f(item.get("price_change_percentage_24h")),
                "change_7d_pct": _f(item.get("price_change_percentage_7d_in_currency")),
                "volume_24h": _f(item.get("total_volume")),
                "rank": item.get("market_cap_rank"),
            })

        data = {"crypto": crypto, "count": len(crypto), "vs_currency": "usd"}
        return self._live_envelope(data, warnings=warnings)

    # =========================================================================
    # 6. vix_term_structure
    # =========================================================================

    def vix_term_structure(self, params: dict) -> dict:  # noqa: ARG002
        """VIX spot and near-term term structure from yfinance."""
        warnings: list[dict] = []

        try:
            _yf()
        except ImportError:
            warnings.append(warn("YFINANCE_MISSING",
                                 detail="yfinance not installed; cannot fetch VIX data"))
            return self._live_envelope(None, warnings=warnings)

        _SYMBOLS = [
            ("^VIX",   "VIX Spot",   0),
            ("^VIX3M", "VIX 3-Month", 90),
            ("^VIX6M", "VIX 6-Month", 180),
            ("VX=F",   "VIX Front-Month Futures", 30),
        ]

        readings: list[tuple[str, str, int, float]] = []  # (symbol, label, days, value)
        for symbol, label, days in _SYMBOLS:
            try:
                hist = _fetch_ticker_history(symbol, period="5d", interval="1d")
                if hist.empty:
                    warnings.append(warn("VIX_NO_DATA", scope=symbol,
                                         detail=f"no data returned for {symbol}"))
                    continue
                closes = hist["Close"].dropna()
                if closes.empty:
                    continue
                val = float(closes.iloc[-1])
                readings.append((symbol, label, days, val))
            except Exception as exc:  # noqa: BLE001
                warnings.append(warn("VIX_FETCH_ERROR", scope=symbol, detail=str(exc)[:200]))

        vix_spot: float | None = None
        vix_3m: float | None = None
        term_structure: list[dict] = []

        for symbol, label, days, value in readings:
            entry = {"label": label, "symbol": symbol, "value": round(value, 2), "days": days}
            term_structure.append(entry)
            if symbol == "^VIX":
                vix_spot = value
            elif symbol == "^VIX3M":
                vix_3m = value

        # Sort by days to maturity
        term_structure.sort(key=lambda x: x["days"])

        # Contango / backwardation
        contango_pct: float | None = None
        regime: str | None = None
        if vix_spot is not None and vix_3m is not None and vix_spot > 0:
            contango_pct = round((vix_3m - vix_spot) / vix_spot * 100, 2)
            regime = "contango" if contango_pct >= 0 else "backwardation"

        data = {
            "vix_spot": round(vix_spot, 2) if vix_spot is not None else None,
            "vix_3m": round(vix_3m, 2) if vix_3m is not None else None,
            "term_structure": term_structure,
            "contango_pct": contango_pct,
            "regime": regime,
            "updated_at": _now_utc().isoformat(),
        }
        return self._live_envelope(data, warnings=warnings)

    # =========================================================================
    # 7. market_tide
    # =========================================================================

    def market_tide(self, params: dict) -> dict:
        """Market-breadth snapshot from the archive ohlcv panel.

        Computes advancing/declining counts and MA-breadth metrics across the
        tracked universe.  Requires a live archive; degrades to ARCHIVE_UNAVAILABLE
        when the gateway is absent.
        """
        if not self.available:
            return self._computed_unavailable()

        lookback = _i(params.get("lookback"), 20, 5, 252)
        warnings: list[dict] = []

        # Pull enough history for 200d MA: lookback + 200 trading days.
        needed_days = lookback + 200

        try:
            rows = self.archive.ohlcv_latest(days=needed_days)  # type: ignore[attr-defined]
        except AttributeError:
            # Older archive gateway may not have ohlcv_latest — fall back to a raw SQL approach.
            try:
                rows = self.archive._rows(  # type: ignore[attr-defined]
                    """
                    SELECT symbol AS ticker, d AS trade_date, c AS close, v AS volume
                    FROM archive.ohlcv
                    WHERE d >= CURRENT_DATE - (%s::int * INTERVAL '1 day')
                    ORDER BY symbol, d
                    """,
                    (needed_days,),
                )
            except Exception as exc:  # noqa: BLE001
                warnings.append(warn("MARKET_TIDE_QUERY_ERROR", detail=str(exc)[:200]))
                return computed_envelope(None, freshness=None, inputs=ARCHIVE_INPUTS,
                                         warnings=warnings)

        if not rows:
            warnings.append(warn("MARKET_TIDE_NO_DATA",
                                  detail="no ohlcv rows returned from archive"))
            return computed_envelope(
                {"advancing": 0, "declining": 0, "unchanged": 0,
                 "adv_dec_ratio": None, "volume_ratio": None,
                 "pct_above_50d": None, "pct_above_200d": None, "regime": "unknown"},
                freshness=None, inputs=ARCHIVE_INPUTS, warnings=warnings,
            )

        # Group rows by ticker.
        from collections import defaultdict  # noqa: PLC0415
        ticker_rows: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            t = r.get("ticker") or r.get("symbol")
            if t:
                ticker_rows[str(t)].append(r)

        # Sort each ticker's series by date.
        for t in ticker_rows:
            ticker_rows[t].sort(key=lambda r: str(r.get("trade_date", "")))

        advancing = 0
        declining = 0
        unchanged = 0
        adv_volume = 0.0
        total_volume = 0.0
        above_50d = 0
        above_200d = 0
        eligible_50 = 0
        eligible_200 = 0

        for ticker, series in ticker_rows.items():
            closes = [_f(r.get("close")) for r in series]
            volumes = [_f(r.get("volume")) or 0.0 for r in series]
            closes_clean = [c for c in closes if c is not None]

            if len(closes_clean) < 2:
                continue

            current = closes_clean[-1]
            vol_today = volumes[-1] if volumes else 0.0

            # Advancing / declining based on trailing `lookback` avg.
            tail = closes_clean[-lookback:] if len(closes_clean) >= lookback else closes_clean
            avg = sum(tail) / len(tail) if tail else None
            if avg is not None:
                if current > avg * 1.001:
                    advancing += 1
                    adv_volume += vol_today
                elif current < avg * 0.999:
                    declining += 1
                else:
                    unchanged += 1
                total_volume += vol_today

            # 50d MA breadth
            if len(closes_clean) >= 50:
                ma50 = sum(closes_clean[-50:]) / 50
                eligible_50 += 1
                if current > ma50:
                    above_50d += 1

            # 200d MA breadth
            if len(closes_clean) >= 200:
                ma200 = sum(closes_clean[-200:]) / 200
                eligible_200 += 1
                if current > ma200:
                    above_200d += 1

        total_dir = advancing + declining + unchanged
        adv_dec_ratio: float | None = None
        if declining > 0:
            adv_dec_ratio = round(advancing / declining, 4)
        elif advancing > 0:
            adv_dec_ratio = float("inf")

        volume_ratio: float | None = None
        if total_volume > 0:
            volume_ratio = round(adv_volume / total_volume, 4)

        pct_above_50d: float | None = None
        if eligible_50 > 0:
            pct_above_50d = round(above_50d / eligible_50 * 100, 2)

        pct_above_200d: float | None = None
        if eligible_200 > 0:
            pct_above_200d = round(above_200d / eligible_200 * 100, 2)

        # Regime classification
        regime = "neutral"
        if pct_above_50d is not None:
            if pct_above_50d >= 70:
                regime = "bullish"
            elif pct_above_50d <= 30:
                regime = "bearish"

        data = {
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "total_tickers": total_dir,
            "adv_dec_ratio": adv_dec_ratio,
            "volume_ratio": volume_ratio,
            "pct_above_50d": pct_above_50d,
            "pct_above_200d": pct_above_200d,
            "regime": regime,
            "lookback_days": lookback,
        }
        return computed_envelope(data,
                                  freshness=freshness_of(rows),
                                  inputs=ARCHIVE_INPUTS,
                                  warnings=warnings)
