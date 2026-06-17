"""SEC EDGAR 13F institutional-holdings source.

Two responsibilities, both built on real SEC data only:

1. ``cusip_ticker_map`` — a CUSIP<->ticker dictionary. 13F info tables identify
   positions by 9-character CUSIP, never by ticker, so to answer "who owns AAPL"
   we need a CUSIP for AAPL (and a ticker for every CUSIP we store). The SEC's
   own Fails-to-Deliver ("FTD") files are a free, key-less, authoritative
   CUSIP|SYMBOL feed covering essentially every actively-traded US security.
   Merging a few recent half-month files yields ~15k mappings with full coverage
   of the names institutions actually hold. Name-matching is deliberately NOT
   used (it mis-resolves abbreviated 13F issuer names ~60% of the time).

2. ``fetch_13f_holdings`` — parse a manager's most recent 13F-HR information
   tables into aggregated positions. Reuses the shared EDGAR client (CIK
   submissions feed, throttle, filing index) from ``edgar``.

Everything is live from SEC. Nothing is imputed: a CUSIP we cannot resolve to a
ticker is kept with ``ticker=None`` and surfaced honestly downstream.
"""
from __future__ import annotations

import io
import logging
import threading
import time
import zipfile
from datetime import date
from typing import Dict, List, Optional, Tuple
import defusedxml.ElementTree as ET

from . import edgar

log = logging.getLogger("agentic.sources.thirteenf")

# --------------------------------------------------------------------------- #
# CUSIP <-> ticker map (SEC Fails-to-Deliver files)
# --------------------------------------------------------------------------- #
# Pipe-delimited columns: SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE
_FTD_URL = "https://www.sec.gov/files/data/fails-deliver-data/cnsfails{ym}{half}.zip"
# Merge this many recent half-month files; 3 is enough for full coverage of the
# names institutions hold while keeping the cold-build cheap.
_FTD_FILES = 3
# How far back (months) to look for available FTD files before giving up. The
# SEC publishes with a few weeks' lag, so the current month is usually absent.
_FTD_LOOKBACK_MONTHS = 6

_cusip_lock = threading.Lock()
_cusip2ticker: Optional[Dict[str, str]] = None
_ticker2cusip: Optional[Dict[str, str]] = None
_cusip_loaded_at = 0.0
_CUSIP_TTL = 24 * 3600.0  # the FTD map changes slowly; refresh daily


def _recent_year_months(n_back: int) -> List[Tuple[int, int]]:
    today = date.today()
    out: List[Tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(n_back + 1):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def _fetch_ftd_file(year: int, month: int, half: str) -> Optional[List[str]]:
    """Download and unzip one FTD half-month file. Returns its lines, or None if
    the file does not exist yet (SEC publishing lag) — never raises for a 404."""
    url = _FTD_URL.format(ym=f"{year:04d}{month:02d}", half=half)
    try:
        resp = edgar._get(url)
    except Exception as exc:  # noqa: BLE001
        log.debug("FTD fetch failed %s: %s", url, exc)
        return None
    if resp.status_code != 200 or not resp.content:
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        raw = zf.read(zf.namelist()[0])
    except Exception as exc:  # noqa: BLE001
        log.debug("FTD unzip failed %s: %s", url, exc)
        return None
    return raw.decode("latin-1", "replace").splitlines()


def _build_cusip_map() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Merge several recent FTD files into CUSIP->ticker and ticker->CUSIP maps."""
    c2t: Dict[str, str] = {}
    files_used = 0
    for (year, month) in _recent_year_months(_FTD_LOOKBACK_MONTHS):
        for half in ("b", "a"):  # later half first (more recent)
            if files_used >= _FTD_FILES:
                break
            lines = _fetch_ftd_file(year, month, half)
            if not lines:
                continue
            files_used += 1
            for ln in lines[1:]:  # skip header
                parts = ln.split("|")
                if len(parts) < 5:
                    continue
                cusip = parts[1].strip().upper()
                sym = parts[2].strip().upper()
                if len(cusip) != 9 or not sym or sym == ".":
                    continue
                # First write wins: more-recent files are processed first, so the
                # freshest CUSIP->ticker assignment is preserved.
                c2t.setdefault(cusip, sym)
        if files_used >= _FTD_FILES:
            break
    t2c: Dict[str, str] = {}
    for cusip, sym in c2t.items():
        t2c.setdefault(sym, cusip)
    return c2t, t2c


def cusip_ticker_map(force: bool = False) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return ``(cusip->ticker, ticker->cusip)``, cached for a day. Raises only
    if no FTD file could be fetched at all (so callers fall back honestly)."""
    global _cusip2ticker, _ticker2cusip, _cusip_loaded_at
    with _cusip_lock:
        fresh = (
            _cusip2ticker is not None
            and (time.monotonic() - _cusip_loaded_at) < _CUSIP_TTL
        )
        if fresh and not force:
            return _cusip2ticker, _ticker2cusip  # type: ignore[return-value]
    c2t, t2c = _build_cusip_map()
    if not c2t:
        raise ValueError("SEC FTD files unavailable; cannot map CUSIPs to tickers")
    with _cusip_lock:
        _cusip2ticker = c2t
        _ticker2cusip = t2c
        _cusip_loaded_at = time.monotonic()
    return c2t, t2c


def resolve_ticker_cusip(ticker: str) -> Optional[str]:
    """CUSIP for a ticker (for the 'who owns <ticker>' lookup), or None."""
    sym = (ticker or "").upper().strip()
    if not sym:
        return None
    try:
        _, t2c = cusip_ticker_map()
    except Exception as exc:  # noqa: BLE001
        log.warning("ticker->cusip resolution failed (%s): %s", sym, exc)
        return None
    return t2c.get(sym) or t2c.get(sym.replace(".", "-")) or t2c.get(sym.replace("-", "."))


# --------------------------------------------------------------------------- #
# 13F information-table parsing
# --------------------------------------------------------------------------- #
# After 2023-01-03 the <value> element is reported in WHOLE DOLLARS; older
# filings reported it in THOUSANDS. We scale pre-2023 filings up so all stored
# market values are in dollars.
_VALUE_DOLLARS_CUTOFF = "2023-01-03"


def _num(v: Optional[str]) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _info_table_url(cik10: str, accession: str) -> Optional[str]:
    """Find the information-table XML inside a filing dir via its index.json.

    The info table is the .xml document that is NOT ``primary_doc.xml`` (the
    cover page). Returns the absolute URL or None if the dir has no info table."""
    cik_int = str(int(cik10))
    nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{nodash}"
    idx = edgar._get(f"{base}/index.json").json()
    items = ((idx.get("directory") or {}).get("item")) or []
    xmls = [
        it.get("name", "") for it in items
        if str(it.get("name", "")).lower().endswith(".xml")
    ]
    info = [f for f in xmls if f.lower() != "primary_doc.xml"]
    if not info:
        return None
    return f"{base}/{info[0]}"


def _parse_info_table(xml_text: str, *, scale_thousands: bool,
                      cusip2ticker: Dict[str, str]) -> List[dict]:
    """Parse a 13F information table into aggregated positions.

    Duplicate (cusip, putCall) rows — common when a holding is split across
    several other managers — are summed. Namespaces are handled with the ``{*}``
    wildcard (some filers, e.g. Citadel, declare prefixes that break naive
    namespace-stripping)."""
    root = ET.fromstring(xml_text)
    agg: Dict[Tuple[str, str], dict] = {}
    for it in root.findall("{*}infoTable"):
        cusip = (it.findtext("{*}cusip") or "").strip().upper()
        if not cusip:
            continue
        name = (it.findtext("{*}nameOfIssuer") or "").strip()
        title = (it.findtext("{*}titleOfClass") or "").strip()
        put_call = (it.findtext("{*}putCall") or "").strip()
        value = _num(it.findtext("{*}value"))
        if scale_thousands:
            value *= 1000.0
        sb = it.find("{*}shrsOrPrnAmt")
        shares = _num(sb.findtext("{*}sshPrnamt") if sb is not None else None)
        sh_type = ((sb.findtext("{*}sshPrnamtType") if sb is not None else "") or "").strip()
        key = (cusip, put_call)
        row = agg.get(key)
        if row is None:
            row = {
                "cusip": cusip,
                "ticker": cusip2ticker.get(cusip),
                "name": name,
                "titleOfClass": title,
                "sharesType": sh_type or "SH",
                "putCall": put_call,
                "value": 0.0,
                "shares": 0.0,
            }
            agg[key] = row
        row["value"] += value
        row["shares"] += shares
    return list(agg.values())


def fetch_13f_holdings(cik10: str, *, max_quarters: int = 2) -> List[dict]:
    """Fetch and parse the most recent ``max_quarters`` 13F-HR filings for a
    manager CIK, newest period first.

    Each element is a period dict::

        {period, filingDate, accession, form, url, totalValue, count, holdings:[...]}

    ``holdings`` are aggregated positions (see ``_parse_info_table``). Periods
    that fail to fetch/parse are skipped (logged), never faked."""
    try:
        cusip2ticker, _ = cusip_ticker_map()
    except Exception as exc:  # noqa: BLE001
        log.warning("13F fetch aborted (no CUSIP map): %s", exc)
        cusip2ticker = {}

    subs = edgar.fetch_submissions(cik10)
    filings = [
        f for f in edgar._recent_filings(subs)
        if str(f.get("form", "")).upper().startswith("13F-HR")
    ]
    # Group ALL 13F-HR filings (originals + amendments) by report period.
    by_period: Dict[str, List[dict]] = {}
    for f in filings:
        period = f.get("reportDate")
        if not period:
            continue
        by_period.setdefault(period, []).append(f)
    periods = sorted(by_period.keys(), reverse=True)[:max_quarters]

    out: List[dict] = []
    for period in periods:
        # A quarter may have several filings: the original 13F-HR plus
        # amendments (13F-HR/A). Amendments are NOT always full restatements —
        # an SEC "NEW HOLDINGS" amendment lists only the added positions, so
        # blindly taking the latest accession would discard the full portfolio
        # and falsely report the rest as "exited". Parse each candidate
        # (newest first) and keep the MOST COMPLETE information table, i.e. the
        # one with the largest holdings count (ties broken by recency). Never
        # merge/impute — we surface a single real filing as the snapshot.
        candidates = sorted(
            by_period[period],
            key=lambda f: (f.get("filingDate") or ""),
            reverse=True,
        )
        best: dict | None = None
        for f in candidates:
            acc = f.get("accession")
            if not acc:
                continue
            try:
                url = _info_table_url(cik10, acc)
                if not url:
                    log.info("13F %s %s: no info table in filing", cik10, period)
                    continue
                xml_text = edgar._get(url).text
                scale = (f.get("filingDate") or "") < _VALUE_DOLLARS_CUTOFF
                holdings = _parse_info_table(
                    xml_text, scale_thousands=scale, cusip2ticker=cusip2ticker,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("13F parse failed %s %s: %s", cik10, period, exc)
                continue
            if not holdings:
                continue
            rec = {
                "period": period,
                "filingDate": f.get("filingDate"),
                "accession": acc,
                "form": f.get("form"),
                "url": edgar.filing_index_url(cik10, acc),
                "totalValue": sum(h["value"] for h in holdings),
                "count": len(holdings),
                "holdings": holdings,
            }
            if best is None or rec["count"] > best["count"]:
                best = rec
        if best is not None:
            out.append(best)
    return out
