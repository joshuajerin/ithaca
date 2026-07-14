"""Extended skill catalog: seasonality, vol surface analytics, technicals, dividends.

These skills are pure-math layers on top of the same v1 archive series used by the core
SkillSet.  They follow the identical envelope/provenance contract so they can be wired into
the MCP server without any additional plumbing.

Import pattern (matches skillset.py):
    from .extended_skills import ExtendedSkills
    EXTENDED_SKILLS = {...}  # dot-name -> method_name
"""
from __future__ import annotations

import math
from calendar import month_abbr
from typing import Any

import numpy as np

from .archive import ArchiveGateway
from .envelope import ARCHIVE_UNAVAILABLE, computed_envelope, freshness_of, warn

__all__ = ["ExtendedSkills"]

# When a COMPUTED skill runs its math over REAL archive series its provenance records this.
ARCHIVE_INPUTS = "ithaca-v1-archive"

# Trading-days per year constant (mirrors compute.py)
_TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# Tiny typed helpers — exact copies of skillset.py _f / _i
# ---------------------------------------------------------------------------

def _f(v: Any) -> float | None:
    """Best-effort float (None-safe)."""
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


# ---------------------------------------------------------------------------
# Private math helpers (no archive I/O, no side-effects)
# ---------------------------------------------------------------------------

def _log_returns(closes: list[float]) -> np.ndarray:
    """Log returns from a list of positive closes."""
    c = np.asarray([x for x in closes if x is not None], dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if c.size < 2:
        return np.array([], dtype=float)
    return np.log(c[1:] / c[:-1])


def _realized_vol_window(closes: list[float], window: int) -> float | None:
    """Annualized realized vol over the trailing *window* closes."""
    tail = closes[-(window + 1):] if len(closes) >= window + 1 else closes
    r = _log_returns(tail)
    if r.size < 2:
        return None
    return float(r.std(ddof=1)) * math.sqrt(_TRADING_DAYS)


def _hurst_rs(log_prices: np.ndarray) -> float | None:
    """Classic R/S Hurst exponent estimate.

    Uses log-log regression of R/S vs sub-series length over a set of
    sub-series sizes. Returns None when the series is too short.
    """
    n = log_prices.size
    if n < 20:
        return None

    # candidate sub-series lengths: powers of 2 from 8 up to n//2
    lengths = [2 ** k for k in range(3, int(math.log2(n)))]
    lengths = [length for length in lengths if length >= 8 and length <= n // 2]
    if len(lengths) < 3:
        return None

    log_ns: list[float] = []
    log_rs_vals: list[float] = []
    for sub_n in lengths:
        num_sub = n // sub_n
        rs_list: list[float] = []
        for i in range(num_sub):
            chunk = log_prices[i * sub_n: (i + 1) * sub_n]
            mean = chunk.mean()
            demeaned = chunk - mean
            cumsum = np.cumsum(demeaned)
            r_val = cumsum.max() - cumsum.min()
            s_val = chunk.std(ddof=1)
            if s_val > 0:
                rs_list.append(r_val / s_val)
        if rs_list:
            log_ns.append(math.log(sub_n))
            log_rs_vals.append(math.log(np.mean(rs_list)))

    if len(log_ns) < 3:
        return None

    # OLS slope = Hurst exponent
    x = np.array(log_ns)
    y = np.array(log_rs_vals)
    slope = float(np.polyfit(x, y, 1)[0])
    return round(slope, 4)


def _rsi(closes: np.ndarray, period: int = 14) -> float | None:
    """Wilder RSI for the most recent bar."""
    if closes.size < period + 1:
        return None
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - 100.0 / (1.0 + rs), 4)


def _ema(series: np.ndarray, span: int) -> np.ndarray:
    """Exponential moving average (pandas-style ewm span)."""
    alpha = 2.0 / (span + 1)
    result = np.empty(series.size)
    result[0] = series[0]
    for i in range(1, series.size):
        result[i] = alpha * series[i] + (1 - alpha) * result[i - 1]
    return result


def _macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> dict | None:
    """MACD line, signal, histogram for the last bar."""
    if closes.size < slow + signal:
        return None
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = ema_fast - ema_slow
    sig_line = _ema(macd_line, signal)
    hist = macd_line - sig_line
    return {
        "macd": round(float(macd_line[-1]), 6),
        "signal": round(float(sig_line[-1]), 6),
        "histogram": round(float(hist[-1]), 6),
    }


def _bollinger(closes: np.ndarray, period: int = 20, n_std: float = 2.0) -> dict | None:
    """Bollinger Bands and %B for the last bar."""
    if closes.size < period:
        return None
    window = closes[-period:]
    middle = float(window.mean())
    std = float(window.std(ddof=1))
    upper = middle + n_std * std
    lower = middle - n_std * std
    last = float(closes[-1])
    band_width = upper - lower
    pct_b = (last - lower) / band_width if band_width > 0 else 0.5
    return {
        "upper": round(upper, 6),
        "middle": round(middle, 6),
        "lower": round(lower, 6),
        "pct_b": round(pct_b, 6),
    }


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float | None:
    """Average True Range (Wilder smoothing) for the last bar."""
    n = min(highs.size, lows.size, closes.size)
    if n < period + 1:
        return None
    h = highs[-n:]
    lows_tail = lows[-n:]
    c = closes[-n:]
    trs = np.maximum(h[1:] - lows_tail[1:],
           np.maximum(np.abs(h[1:] - c[:-1]), np.abs(lows_tail[1:] - c[:-1])))
    if trs.size < period:
        return None
    atr_val = float(trs[-period:].mean())
    return round(atr_val, 6)


# ---------------------------------------------------------------------------
# ExtendedSkills class
# ---------------------------------------------------------------------------

class ExtendedSkills:
    """Extended skill catalog layered on top of the v1 ArchiveGateway.

    Instantiated by passing the same ``ArchiveGateway`` (or ``None``) used by
    ``SkillSet``.  Every method returns the canonical provenance envelope so the
    MCP server can dispatch them without special-casing.
    """

    def __init__(self, archive: ArchiveGateway | None) -> None:
        self.archive = archive
        self.available = archive is not None

    def _computed_unavailable(self) -> dict:
        return {"data": None, "provenance": {"source": "computed"}, "warnings": [ARCHIVE_UNAVAILABLE]}

    # ------------------------------------------------------------------
    # 1. seasonality_monthly
    # ------------------------------------------------------------------
    def seasonality_monthly(self, params: dict) -> dict:
        """Average return, win-rate, and median return per calendar month (Jan-Dec).

        Uses the full OHLCV history up to *years* years. Returns NaN-free results;
        months with no data are omitted rather than returned with nulls.
        """
        if not self.available:
            return self._computed_unavailable()

        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("seasonality.monthly needs a 'symbol'.")
        years = _i(params.get("years"), 10, 1, 50)

        bars = self.archive.ohlcv(symbol)
        if not bars:
            warnings = [warn("NO_DATA", scope=symbol, detail="no OHLCV bars found")]
            return computed_envelope({"symbol": symbol, "years": years, "months": []},
                                     freshness=None, inputs=ARCHIVE_INPUTS, warnings=warnings)

        # Build (year, month, monthly_return) triples from the bar list.
        # Bars are expected in ascending date order; we use open-of-month / close-of-month
        # derived from the daily bars by grouping on (year, month).
        from collections import defaultdict

        by_ym: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for b in bars:
            ts = str(b.get("t") or b.get("date") or "")
            if len(ts) < 7:
                continue
            try:
                yr, mo = int(ts[:4]), int(ts[5:7])
            except ValueError:
                continue
            by_ym[(yr, mo)].append(b)

        if not by_ym:
            return computed_envelope({"symbol": symbol, "years": years, "months": []},
                                     freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

        # Only use the trailing *years* calendar years.
        all_years = sorted({k[0] for k in by_ym})
        cutoff_year = all_years[-1] - years + 1
        by_ym = {k: v for k, v in by_ym.items() if k[0] >= cutoff_year}

        # Compute monthly return = (last_close - first_open) / first_open (or close-to-close).
        month_rets: dict[int, list[float]] = defaultdict(list)
        for (yr, mo), day_bars in sorted(by_ym.items()):
            day_bars_s = sorted(day_bars, key=lambda b: str(b.get("t") or b.get("date") or ""))
            first_open = _f(day_bars_s[0].get("o") or day_bars_s[0].get("c"))
            last_close = _f(day_bars_s[-1].get("c"))
            if first_open and last_close and first_open > 0:
                month_rets[mo].append((last_close - first_open) / first_open)

        _MONTH_NAMES = list(month_abbr)  # ['', 'Jan', 'Feb', ..., 'Dec']
        months_out = []
        for mo in range(1, 13):
            rets = month_rets.get(mo, [])
            if not rets:
                continue
            arr = np.array(rets)
            months_out.append({
                "month": mo,
                "month_name": _MONTH_NAMES[mo],
                "avg_return": round(float(arr.mean()), 6),
                "median_return": round(float(np.median(arr)), 6),
                "win_rate": round(float((arr > 0).mean()), 4),
                "count": len(rets),
            })

        data = {"symbol": symbol, "years": years, "months": months_out}
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

    # ------------------------------------------------------------------
    # 2. seasonality_heatmap
    # ------------------------------------------------------------------
    def seasonality_heatmap(self, params: dict) -> dict:
        """Month × year return matrix for a symbol.

        Returns a flat list of {year, month, return} records (the *heatmap*) plus a
        summary noting the best and worst calendar months by average return.
        """
        if not self.available:
            return self._computed_unavailable()

        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("seasonality.heatmap needs a 'symbol'.")
        years = _i(params.get("years"), 10, 1, 50)

        bars = self.archive.ohlcv(symbol)
        if not bars:
            warnings = [warn("NO_DATA", scope=symbol, detail="no OHLCV bars found")]
            return computed_envelope({"symbol": symbol, "years_covered": 0, "heatmap": [],
                                      "summary": {"best_month": None, "worst_month": None}},
                                     freshness=None, inputs=ARCHIVE_INPUTS, warnings=warnings)

        from collections import defaultdict

        by_ym: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for b in bars:
            ts = str(b.get("t") or b.get("date") or "")
            if len(ts) < 7:
                continue
            try:
                yr, mo = int(ts[:4]), int(ts[5:7])
            except ValueError:
                continue
            by_ym[(yr, mo)].append(b)

        all_years = sorted({k[0] for k in by_ym})
        if not all_years:
            return computed_envelope({"symbol": symbol, "years_covered": 0, "heatmap": [],
                                      "summary": {"best_month": None, "worst_month": None}},
                                     freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

        cutoff_year = all_years[-1] - years + 1
        by_ym = {k: v for k, v in by_ym.items() if k[0] >= cutoff_year}

        heatmap: list[dict] = []
        month_bucket: dict[int, list[float]] = defaultdict(list)
        _MONTH_NAMES = list(month_abbr)

        for (yr, mo), day_bars in sorted(by_ym.items()):
            day_bars_s = sorted(day_bars, key=lambda b: str(b.get("t") or b.get("date") or ""))
            first_open = _f(day_bars_s[0].get("o") or day_bars_s[0].get("c"))
            last_close = _f(day_bars_s[-1].get("c"))
            if first_open and last_close and first_open > 0:
                ret = (last_close - first_open) / first_open
                heatmap.append({"year": yr, "month": mo,
                                 "month_name": _MONTH_NAMES[mo],
                                 "return": round(ret, 6)})
                month_bucket[mo].append(ret)

        # Summary: best/worst month by average return
        best_month = worst_month = None
        if month_bucket:
            avgs = {mo: float(np.mean(v)) for mo, v in month_bucket.items()}
            bm = max(avgs, key=avgs.__getitem__)
            wm = min(avgs, key=avgs.__getitem__)
            best_month = {"month": bm, "month_name": _MONTH_NAMES[bm],
                          "avg_return": round(avgs[bm], 6)}
            worst_month = {"month": wm, "month_name": _MONTH_NAMES[wm],
                           "avg_return": round(avgs[wm], 6)}

        covered_years = len({e["year"] for e in heatmap})
        data = {"symbol": symbol, "years_covered": covered_years, "heatmap": heatmap,
                "summary": {"best_month": best_month, "worst_month": worst_month}}
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

    # ------------------------------------------------------------------
    # 3. vol_iv_rank
    # ------------------------------------------------------------------
    def vol_iv_rank(self, params: dict) -> dict:
        """IV Rank and IV Percentile using realized vol as an IV proxy.

        IV Rank  = (current_rv - min_rv_1y) / (max_rv_1y - min_rv_1y) * 100
        IV Percentile = percentile rank of current_rv in the trailing lookback distribution.

        Both are reported on a 0–100 scale.
        """
        if not self.available:
            return self._computed_unavailable()

        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("vol.iv_rank needs a 'symbol'.")
        lookback = _i(params.get("lookback"), 252, 20, 1000)

        bars = self.archive.ohlcv(symbol)
        closes = [_f(b.get("c")) for b in bars if _f(b.get("c")) is not None]

        if len(closes) < 22:
            warnings = [warn("INSUFFICIENT_DATA", scope=symbol,
                             detail=f"need at least 22 closes, have {len(closes)}")]
            return computed_envelope(
                {"symbol": symbol, "iv_rank": None, "iv_percentile": None,
                 "current_rv": None, "min_rv_1y": None, "max_rv_1y": None,
                 "lookback": lookback},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        # Rolling 20-day realized vol series, one value per day
        rv_series: list[float] = []
        for i in range(20, len(closes) + 1):
            rv = _realized_vol_window(closes[max(0, i - 21):i], 20)
            if rv is not None:
                rv_series.append(rv)

        if not rv_series:
            warnings = [warn("INSUFFICIENT_DATA", scope=symbol,
                             detail="cannot compute rolling 20d RV series")]
            return computed_envelope(
                {"symbol": symbol, "iv_rank": None, "iv_percentile": None,
                 "current_rv": None, "min_rv_1y": None, "max_rv_1y": None,
                 "lookback": lookback},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        rv_arr = np.array(rv_series[-lookback:])
        current_rv = float(rv_arr[-1])
        min_rv = float(rv_arr.min())
        max_rv = float(rv_arr.max())

        iv_rank = None
        if max_rv > min_rv:
            iv_rank = round((current_rv - min_rv) / (max_rv - min_rv) * 100, 2)
        elif max_rv == min_rv:
            iv_rank = 50.0

        iv_percentile = round(float((rv_arr <= current_rv).mean() * 100), 2)

        data = {
            "symbol": symbol,
            "iv_rank": iv_rank,
            "iv_percentile": iv_percentile,
            "current_rv": round(current_rv, 6),
            "min_rv_1y": round(min_rv, 6),
            "max_rv_1y": round(max_rv, 6),
            "lookback": lookback,
        }
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

    # ------------------------------------------------------------------
    # 4. vol_vrp
    # ------------------------------------------------------------------
    def vol_vrp(self, params: dict) -> dict:
        """Variance Risk Premium (VRP): realized vol differential as a vol-selling signal.

        VRP = forward realized vol (next forward_window days) − trailing realized vol
              (trailing window days).  Computed historically over the full bar series;
              the most-recent non-lookahead value is returned as ``vrp_current``.

        A positive VRP mean historically means realized vol tends to come in BELOW
        implied vol → sell-vol signal.  A negative mean → buy-vol signal.
        """
        if not self.available:
            return self._computed_unavailable()

        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("vol.vrp needs a 'symbol'.")
        window = _i(params.get("window"), 30, 5, 252)
        fwd_window = _i(params.get("forward_window"), 21, 5, 252)

        bars = self.archive.ohlcv(symbol)
        closes = [_f(b.get("c")) for b in bars if _f(b.get("c")) is not None]
        min_len = window + fwd_window + 2
        if len(closes) < min_len:
            warnings = [warn("INSUFFICIENT_DATA", scope=symbol,
                             detail=f"need {min_len} closes, have {len(closes)}")]
            return computed_envelope(
                {"symbol": symbol, "vrp_mean": None, "vrp_std": None,
                 "vrp_current": None, "vrp_signal": None, "window": window},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        vrp_series: list[float] = []
        # For each point t, trailing RV uses closes[t-window-1 : t],
        # forward RV uses closes[t : t+fwd_window+1].
        # We stop at len(closes) - fwd_window - 1 so the forward window is fully realized.
        for t in range(window + 1, len(closes) - fwd_window):
            trailing_rv = _realized_vol_window(closes[t - window - 1: t], window)
            forward_rv = _realized_vol_window(closes[t: t + fwd_window + 1], fwd_window)
            if trailing_rv is not None and forward_rv is not None:
                vrp_series.append(forward_rv - trailing_rv)

        if not vrp_series:
            warnings = [warn("INSUFFICIENT_DATA", scope=symbol,
                             detail="could not compute any VRP observations")]
            return computed_envelope(
                {"symbol": symbol, "vrp_mean": None, "vrp_std": None,
                 "vrp_current": None, "vrp_signal": None, "window": window},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        arr = np.array(vrp_series)
        vrp_mean = float(arr.mean())
        vrp_std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
        vrp_current = float(arr[-1])

        # Signal: positive mean → sell vol (IV premium over RV), negative → buy vol
        vrp_signal = "sell_vol" if vrp_mean > 0 else "buy_vol"

        data = {
            "symbol": symbol,
            "vrp_mean": round(vrp_mean, 6),
            "vrp_std": round(vrp_std, 6),
            "vrp_current": round(vrp_current, 6),
            "vrp_signal": vrp_signal,
            "window": window,
            "forward_window": fwd_window,
            "observations": len(vrp_series),
        }
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

    # ------------------------------------------------------------------
    # 5. vol_anomaly_score
    # ------------------------------------------------------------------
    def vol_anomaly_score(self, params: dict) -> dict:
        """Z-score of current 20d realized vol vs its trailing distribution.

        Helps detect vol regime breaks: z > 1.5 = elevated ("high"), z < -1.5 =
        suppressed ("low"), otherwise "normal".
        """
        if not self.available:
            return self._computed_unavailable()

        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("vol.anomaly_score needs a 'symbol'.")
        window = _i(params.get("window"), 252, 21, 2000)

        bars = self.archive.ohlcv(symbol)
        closes = [_f(b.get("c")) for b in bars if _f(b.get("c")) is not None]

        if len(closes) < 22:
            warnings = [warn("INSUFFICIENT_DATA", scope=symbol,
                             detail=f"need at least 22 closes, have {len(closes)}")]
            return computed_envelope(
                {"symbol": symbol, "z_score": None, "current_rv_20d": None,
                 "mean_rv": None, "std_rv": None, "window": window,
                 "interpretation": None},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        # Build rolling 20d RV series
        rv_series: list[float] = []
        for i in range(21, len(closes) + 1):
            rv = _realized_vol_window(closes[max(0, i - 21): i], 20)
            if rv is not None:
                rv_series.append(rv)

        if len(rv_series) < 2:
            warnings = [warn("INSUFFICIENT_DATA", scope=symbol,
                             detail="not enough rolling RV observations")]
            return computed_envelope(
                {"symbol": symbol, "z_score": None, "current_rv_20d": None,
                 "mean_rv": None, "std_rv": None, "window": window,
                 "interpretation": None},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        rv_arr = np.array(rv_series[-window:])
        current_rv = float(rv_arr[-1])
        mean_rv = float(rv_arr.mean())
        std_rv = float(rv_arr.std(ddof=1))

        z_score: float | None = None
        if std_rv > 0:
            z_score = round((current_rv - mean_rv) / std_rv, 4)

        if z_score is None:
            interpretation = "normal"
        elif z_score > 1.5:
            interpretation = "high"
        elif z_score < -1.5:
            interpretation = "low"
        else:
            interpretation = "normal"

        data = {
            "symbol": symbol,
            "z_score": z_score,
            "current_rv_20d": round(current_rv, 6),
            "mean_rv": round(mean_rv, 6),
            "std_rv": round(std_rv, 6),
            "window": window,
            "interpretation": interpretation,
        }
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

    # ------------------------------------------------------------------
    # 6. vol_character
    # ------------------------------------------------------------------
    def vol_character(self, params: dict) -> dict:
        """Classify volatility character using the Hurst exponent (R/S analysis).

        H > 0.55 → trending (persistent), H < 0.45 → mean-reverting (antipersistent),
        0.45 ≤ H ≤ 0.55 → random walk.
        """
        if not self.available:
            return self._computed_unavailable()

        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("vol.character needs a 'symbol'.")
        window = _i(params.get("window"), 252, 30, 5000)

        bars = self.archive.ohlcv(symbol)
        closes = [_f(b.get("c")) for b in bars if _f(b.get("c")) is not None]

        if len(closes) < 30:
            warnings = [warn("INSUFFICIENT_DATA", scope=symbol,
                             detail=f"need at least 30 closes, have {len(closes)}")]
            return computed_envelope(
                {"symbol": symbol, "hurst_exponent": None, "character": None,
                 "window": window},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        tail = closes[-window:] if len(closes) > window else closes
        log_prices = np.log(np.array([c for c in tail if c and c > 0], dtype=float))

        hurst = _hurst_rs(log_prices)

        character: str | None = None
        if hurst is not None:
            if hurst > 0.55:
                character = "trending"
            elif hurst < 0.45:
                character = "mean-reverting"
            else:
                character = "random-walk"

        warnings_out = None
        if hurst is None:
            warnings_out = [warn("INSUFFICIENT_DATA", scope=symbol,
                                 detail="not enough data for reliable R/S estimate")]

        data = {
            "symbol": symbol,
            "hurst_exponent": hurst,
            "character": character,
            "window": len(tail),
        }
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS,
                                 warnings=warnings_out)

    # ------------------------------------------------------------------
    # 7. technical_indicators
    # ------------------------------------------------------------------
    def technical_indicators(self, params: dict) -> dict:
        """RSI(14), MACD(12,26,9), Bollinger Bands(20,2), ATR(14) on archive OHLCV.

        ``range`` is a convenience string parsed into a bar count:
          "1mo" → 21, "3mo" → 63, "6mo" → 126, "1y" → 252 (default), "2y" → 504.
        """
        if not self.available:
            return self._computed_unavailable()

        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("technical.indicators needs a 'symbol'.")

        _RANGE_MAP = {"1mo": 21, "3mo": 63, "6mo": 126, "1y": 252, "2y": 504, "5y": 1260}
        range_str = str(params.get("range") or "6mo").lower().strip()
        bar_limit = _RANGE_MAP.get(range_str, 126)

        bars = self.archive.ohlcv(symbol)
        if not bars:
            warnings = [warn("NO_DATA", scope=symbol, detail="no OHLCV bars found")]
            return computed_envelope(
                {"symbol": symbol, "as_of": None, "rsi": None, "macd": None,
                 "bollinger": None, "atr": None, "trend_signal": None},
                freshness=None, inputs=ARCHIVE_INPUTS, warnings=warnings)

        # Take the trailing bar_limit bars (plus a buffer for indicator warm-up)
        warm_up = 60
        tail_bars = bars[-(bar_limit + warm_up):]

        closes_raw = [_f(b.get("c")) for b in tail_bars]
        highs_raw = [_f(b.get("h")) or _f(b.get("c")) for b in tail_bars]
        lows_raw = [_f(b.get("l")) or _f(b.get("c")) for b in tail_bars]

        # Filter to finite positives, aligned
        valid = [(c, h, lo) for c, h, lo in zip(closes_raw, highs_raw, lows_raw)
                 if c and h and lo and c > 0 and h > 0 and lo > 0]
        if len(valid) < 30:
            warnings = [warn("INSUFFICIENT_DATA", scope=symbol,
                             detail=f"only {len(valid)} usable bars")]
            return computed_envelope(
                {"symbol": symbol, "as_of": None, "rsi": None, "macd": None,
                 "bollinger": None, "atr": None, "trend_signal": None},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        closes_np = np.array([v[0] for v in valid], dtype=float)
        highs_np = np.array([v[1] for v in valid], dtype=float)
        lows_np = np.array([v[2] for v in valid], dtype=float)

        rsi_val = _rsi(closes_np, period=14)
        macd_val = _macd(closes_np, fast=12, slow=26, signal=9)
        bb_val = _bollinger(closes_np, period=20, n_std=2.0)
        atr_val = _atr(highs_np, lows_np, closes_np, period=14)

        last_close = float(closes_np[-1])

        # Determine as_of from the last bar with a timestamp
        as_of: str | None = None
        for b in reversed(tail_bars):
            ts = b.get("t") or b.get("date")
            if ts:
                as_of = str(ts)[:10]
                break

        # Trend signal
        trend_signal = "neutral"
        if bb_val and rsi_val is not None:
            if last_close > bb_val["upper"] and rsi_val > 50:
                trend_signal = "bullish"
            elif last_close < bb_val["lower"] and rsi_val < 50:
                trend_signal = "bearish"

        data = {
            "symbol": symbol,
            "as_of": as_of,
            "rsi": rsi_val,
            "macd": macd_val,
            "bollinger": bb_val,
            "atr": atr_val,
            "trend_signal": trend_signal,
        }
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

    # ------------------------------------------------------------------
    # 8. dividends
    # ------------------------------------------------------------------
    def dividends(self, params: dict) -> dict:
        """Dividend history and trailing-twelve-month yield via yfinance.

        Falls back gracefully when yfinance is unavailable or the ticker pays no
        dividends (e.g. growth stocks).  yield_pct is against the price on the
        dividend date; ttm_yield is against the most-recent close in the archive.
        """
        if not self.available:
            return self._computed_unavailable()

        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("dividends needs a 'symbol'.")
        years = _i(params.get("years"), 5, 1, 20)

        # Fetch current price from archive for yield calculation
        bars = self.archive.ohlcv(symbol)
        current_price: float | None = None
        if bars:
            current_price = _f(bars[-1].get("c"))

        try:
            import yfinance as yf  # optional heavy dependency
        except ImportError:
            warnings = [warn("DEPENDENCY_MISSING", scope=symbol,
                             detail="yfinance is not installed; dividend data unavailable")]
            return computed_envelope(
                {"symbol": symbol, "dividends": [], "ttm_yield": None,
                 "payout_frequency": None, "total_ttm": None},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        try:
            ticker = yf.Ticker(symbol)
            divs = ticker.dividends  # pandas Series indexed by Timestamp
        except Exception as exc:
            warnings = [warn("FETCH_ERROR", scope=symbol, detail=str(exc)[:200])]
            return computed_envelope(
                {"symbol": symbol, "dividends": [], "ttm_yield": None,
                 "payout_frequency": None, "total_ttm": None},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS, warnings=warnings)

        if divs is None or len(divs) == 0:
            return computed_envelope(
                {"symbol": symbol, "dividends": [], "ttm_yield": 0.0,
                 "payout_frequency": "none", "total_ttm": 0.0},
                freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

        # Filter to the trailing *years* years
        import datetime
        cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=years * 365)

        div_list: list[dict] = []
        for ts, amount in divs.items():
            try:
                # pandas Timestamp → datetime
                dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                if dt < cutoff:
                    continue
                amt = float(amount)
                yield_pct: float | None = None
                if current_price and current_price > 0:
                    yield_pct = round(amt / current_price * 100, 4)
                div_list.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "amount": round(amt, 6),
                    "yield_pct": yield_pct,
                })
            except Exception:
                continue

        # TTM: sum dividends in the last 365 days
        ttm_cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=365)
        ttm_divs = []
        for ts, amount in divs.items():
            try:
                dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                if dt >= ttm_cutoff:
                    ttm_divs.append(float(amount))
            except Exception:
                continue

        total_ttm = round(sum(ttm_divs), 6) if ttm_divs else 0.0
        ttm_yield: float | None = None
        if current_price and current_price > 0:
            ttm_yield = round(total_ttm / current_price * 100, 4)

        # Infer payout frequency from TTM dividend count
        ttm_count = len(ttm_divs)
        if ttm_count == 0:
            payout_frequency = "none"
        elif ttm_count == 1:
            payout_frequency = "annual"
        elif ttm_count == 2:
            payout_frequency = "semi-annual"
        elif ttm_count == 4:
            payout_frequency = "quarterly"
        elif ttm_count == 12:
            payout_frequency = "monthly"
        else:
            payout_frequency = f"{ttm_count}x/year"

        data = {
            "symbol": symbol,
            "dividends": div_list,
            "ttm_yield": ttm_yield,
            "payout_frequency": payout_frequency,
            "total_ttm": total_ttm,
        }
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)
