"""SEC EDGAR data client (data.sec.gov + www.sec.gov/Archives).

A small, reusable client for the SEC's free, key-less EDGAR system. It is the
shared foundation other EDGAR-backed features (insider transactions today; 13F
holdings and a filings browser later) build on, so it deliberately exposes the
primitives — ticker→CIK resolution, the company submissions feed and individual
filing documents — rather than only the insider view.

SEC access rules we honour:
  - every request carries a descriptive ``User-Agent`` (SEC blocks anonymous
    traffic and asks for a contact string);
  - traffic stays well under the published ~10 requests/second fair-access limit
    via a process-wide minimum spacing between calls;
  - all calls route through the shared resilient ``request`` helper so throttles
    (429/403/5xx) back off and trip the per-source circuit breaker.

The first consumer is real insider transactions (Forms 4 and 5). We read the
issuer's submissions feed, take its recent ownership filings and parse each
filing's namespace-less ``ownershipDocument`` XML out of the full-submission
text file. Everything returned is real data parsed from the filing; on any
failure we raise (caller logs/skips) or return an empty list — we never
fabricate a trade.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from . import _resilient

log = logging.getLogger("terminal.sources.edgar")

# SEC requires a descriptive User-Agent with a contact. This is a sandboxed demo
# terminal; the contact is a generic mailbox for the project.
_HEADERS = {
    "User-Agent": "AgenticTerminal/1.0 (contact: terminal@example.com)",
    "Accept-Encoding": "gzip, deflate",
}
_TIMEOUT = httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=30.0)
_SOURCE = "sec_edgar"

# Process-wide polite rate limit. SEC's documented ceiling is ~10 req/s; we stay
# comfortably below it with a minimum spacing between successive calls so the
# background loop (which can fan out across many tickers/filings) never bursts.
_MIN_SPACING = 0.15  # seconds between calls (~6.6 req/s worst case)
_rate_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    with _rate_lock:
        wait = _MIN_SPACING - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _get(
    url: str, *, params: Optional[Dict] = None, follow_redirects: bool = True,
) -> httpx.Response:
    _throttle()
    return _resilient.request(
        _SOURCE, url, params=params, headers=_HEADERS, timeout=_TIMEOUT,
        follow_redirects=follow_redirects,
    )


# --------------------------------------------------------------------------- #
# ticker -> CIK resolution
# --------------------------------------------------------------------------- #
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_cik_map: Optional[Dict[str, Tuple[str, str]]] = None  # TICKER -> (cik10, title)
_cik_lock = threading.Lock()
_cik_loaded_at = 0.0
_CIK_TTL = 24 * 3600.0  # the ticker map changes slowly; refresh daily


def _load_cik_map(force: bool = False) -> Dict[str, Tuple[str, str]]:
    """Load and cache the SEC ticker->CIK directory. Raises on fetch failure."""
    global _cik_map, _cik_loaded_at
    with _cik_lock:
        fresh = _cik_map is not None and (time.monotonic() - _cik_loaded_at) < _CIK_TTL
        if fresh and not force:
            return _cik_map
    resp = _get(_TICKERS_URL)
    raw = resp.json()
    mapping: Dict[str, Tuple[str, str]] = {}
    # The file is a dict keyed by row index: {"0": {cik_str, ticker, title}, ...}
    rows = raw.values() if isinstance(raw, dict) else raw
    for row in rows:
        ticker = str(row.get("ticker", "")).upper().strip()
        cik_str = row.get("cik_str")
        if not ticker or cik_str is None:
            continue
        cik10 = str(int(cik_str)).zfill(10)
        mapping[ticker] = (cik10, row.get("title") or ticker)
    if not mapping:
        raise ValueError("SEC company_tickers.json returned no rows")
    with _cik_lock:
        _cik_map = mapping
        _cik_loaded_at = time.monotonic()
    return mapping


def resolve_cik(ticker: str) -> Optional[Tuple[str, str]]:
    """Return ``(cik10, issuerTitle)`` for a US ticker, or ``None`` if unknown.

    EDGAR only covers SEC filers, so foreign-only listings (e.g. SGX codes) and
    unrecognised symbols resolve to ``None`` and the caller reports the feed as
    unavailable rather than guessing.
    """
    sym = (ticker or "").upper().strip()
    if not sym:
        return None
    # EDGAR uses dashes in class tickers (BRK-B); normalise a dot form just in case.
    candidates = [sym, sym.replace(".", "-")]
    try:
        mapping = _load_cik_map()
    except Exception as exc:  # noqa: BLE001
        log.warning("EDGAR ticker map load failed: %s", exc)
        return None
    for c in candidates:
        hit = mapping.get(c)
        if hit:
            return hit
    return None


# --------------------------------------------------------------------------- #
# submissions feed
# --------------------------------------------------------------------------- #
def fetch_submissions(cik10: str) -> Dict:
    """Return the raw submissions JSON for a 10-digit zero-padded CIK."""
    url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
    return _get(url).json()


def _recent_filings(submissions: Dict) -> List[Dict]:
    """Flatten the columnar ``filings.recent`` block into per-filing dicts."""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    accession = recent.get("accessionNumber") or []
    forms = recent.get("form") or []
    fdates = recent.get("filingDate") or []
    rdates = recent.get("reportDate") or []
    descs = recent.get("primaryDocDescription") or []
    sizes = recent.get("size") or []
    primary = recent.get("primaryDocument") or []
    rdates = recent.get("reportDate") or []
    out: List[Dict] = []
    for i, acc in enumerate(accession):
        out.append({
            "accession": acc,
            "form": forms[i] if i < len(forms) else "",
            "filingDate": fdates[i] if i < len(fdates) else None,
            "reportDate": rdates[i] if i < len(rdates) else None,
            "reportDate": (rdates[i] or None) if i < len(rdates) else None,
            "primaryDocDescription": (descs[i] or None) if i < len(descs) else None,
            "size": sizes[i] if i < len(sizes) else None,
            "primaryDocument": primary[i] if i < len(primary) else "",
        })
    return out


# --------------------------------------------------------------------------- #
# Form 4/5 ownership XML
# --------------------------------------------------------------------------- #
_OWNERSHIP_FORMS = ("4", "5")  # Form 3 carries holdings only (no transactions)

# Map SEC transaction codes to a human, sentiment-bearing type.
_CODE_TYPE = {
    "P": "buy",
    "S": "sell",
    "A": "grant",
    "M": "option-exercise",
    "X": "option-exercise",
    "C": "conversion",
    "F": "tax",
    "G": "gift",
    "D": "disposition",
    "W": "inheritance",
}


def _txt_url(cik10: str, accession: str) -> str:
    cik_int = str(int(cik10))
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{nodash}/{accession}.txt"


def filing_index_url(cik10: str, accession: str) -> str:
    """Human-facing EDGAR filing index page for an accession."""
    cik_int = str(int(cik10))
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{nodash}/{accession}-index.htm"


def filing_doc_url(cik10: str, accession: str, document: str) -> str:
    """Direct link to a filing's primary document inside its accession folder."""
    cik_int = str(int(cik10))
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{nodash}/{document}"


# --------------------------------------------------------------------------- #
# Filings browser: recent filings list + EDGAR full-text search
# --------------------------------------------------------------------------- #
# Full-text search backend used by EDGAR's own search UI. It indexes filing
# documents since 2001 and is key-less (still requires the User-Agent header).
_FTS_URL = "https://efts.sec.gov/LATEST/search-index"


def fetch_company_filings(
    ticker: str,
    *,
    cik10: Optional[str] = None,
    forms: Optional[List[str]] = None,
    since_days: Optional[int] = None,
    limit: int = 80,
) -> Dict:
    """Recent filings for an issuer, newest-first, straight from the submissions
    feed. Returns real data only; an unknown ticker yields ``source`` =
    ``"unavailable"`` rather than a fabricated list."""
    sym = (ticker or "").upper().strip()
    title: Optional[str] = None
    if cik10 is None:
        hit = resolve_cik(sym)
        if not hit:
            return {
                "symbol": sym, "cik": None, "issuerName": None,
                "filings": [], "asOf": None, "source": "unavailable",
            }
        cik10, title = hit
    subs = fetch_submissions(cik10)
    title = title or subs.get("name") or sym
    cutoff = (
        (date.today() - timedelta(days=since_days)).isoformat()
        if since_days else None
    )
    want = {f.upper() for f in forms} if forms else None
    rows: List[Dict] = []
    for f in _recent_filings(subs):
        form = str(f.get("form") or "")
        root = form.split("/")[0]
        if want and form.upper() not in want and root.upper() not in want:
            continue
        fdate = f.get("filingDate")
        if cutoff and (fdate or "") < cutoff:
            continue
        acc = f.get("accession") or ""
        doc = f.get("primaryDocument") or ""
        rows.append({
            "form": form,
            "rootForm": root,
            "filingDate": fdate,
            "reportDate": f.get("reportDate"),
            "accession": acc,
            "description": f.get("primaryDocDescription"),
            "size": f.get("size"),
            "documentUrl": (
                filing_doc_url(cik10, acc, doc) if doc
                else filing_index_url(cik10, acc)
            ),
            "indexUrl": filing_index_url(cik10, acc),
        })
        if len(rows) >= limit:
            break
    as_of = max((r["filingDate"] for r in rows if r.get("filingDate")), default=None)
    return {
        "symbol": sym, "cik": cik10, "issuerName": title,
        "filings": rows, "asOf": as_of, "source": "live",
    }


def full_text_search(
    query: str,
    *,
    forms: Optional[List[str]] = None,
    cik10: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 40,
) -> Dict:
    """EDGAR full-text keyword search (filing documents since 2001). Optionally
    scoped to a single issuer (``cik10``), form types and a date range. Returns
    real hits only; an empty query yields no results."""
    q = (query or "").strip()
    if not q:
        return {"query": q, "hits": [], "total": 0, "source": "live"}
    params: Dict[str, str] = {"q": q}
    if forms:
        params["forms"] = ",".join(forms)
    if cik10:
        params["ciks"] = cik10
    if start:
        params["startdt"] = start
    if end:
        params["enddt"] = end
    data = _get(_FTS_URL, params=params).json()
    hits_block = data.get("hits") or {}
    total_raw = hits_block.get("total")
    total = total_raw.get("value") if isinstance(total_raw, dict) else total_raw
    out: List[Dict] = []
    for h in (hits_block.get("hits") or [])[:limit]:
        src = h.get("_source") or {}
        _id = h.get("_id") or ""
        adsh = src.get("adsh") or (_id.split(":", 1)[0] if ":" in _id else _id)
        doc = _id.split(":", 1)[1] if ":" in _id else ""
        ciks = src.get("ciks") or []
        cik_first = ciks[0] if ciks else None
        names = src.get("display_names") or []
        form = src.get("form") or ((src.get("root_forms") or [None])[0])
        out.append({
            "company": names[0] if names else None,
            "cik": cik_first,
            "form": form,
            "rootForm": (form or "").split("/")[0],
            "filingDate": src.get("file_date"),
            "reportDate": src.get("period_ending"),
            "accession": adsh,
            "fileType": src.get("file_type"),
            "description": src.get("file_description"),
            "documentUrl": (
                filing_doc_url(cik_first, adsh, doc)
                if (cik_first and doc) else None
            ),
            "indexUrl": filing_index_url(cik_first, adsh) if cik_first else None,
        })
    return {"query": q, "hits": out, "total": total or 0, "source": "live"}


def _text(node: Optional[ET.Element], path: str) -> Optional[str]:
    if node is None:
        return None
    el = node.find(path)
    if el is None:
        return None
    txt = el.text
    return txt.strip() if isinstance(txt, str) and txt.strip() else None


def _value(node: Optional[ET.Element], path: str) -> Optional[str]:
    """Read ``<path><value>X</value></path>`` (the common Form 345 wrapper)."""
    return _text(node, f"{path}/value")


def _num(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_true(v: Optional[str]) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes"}


def _role(rel: Optional[ET.Element]) -> str:
    # Relationship flags/titles are direct text under reportingOwnerRelationship
    # (NOT <value>-wrapped), so read them with _text.
    if rel is None:
        return "Insider"
    parts: List[str] = []
    if _is_true(_text(rel, "isDirector")):
        parts.append("Director")
    if _is_true(_text(rel, "isOfficer")):
        title = _text(rel, "officerTitle")
        parts.append(f"Officer ({title})" if title else "Officer")
    if _is_true(_text(rel, "isTenPercentOwner")):
        parts.append("10% Owner")
    if _is_true(_text(rel, "isOther")):
        other = _text(rel, "otherText")
        parts.append(other or "Other")
    return ", ".join(parts) if parts else "Insider"


def _parse_ownership_xml(xml: str) -> Optional[ET.Element]:
    start = xml.find("<ownershipDocument")
    end = xml.find("</ownershipDocument>")
    if start == -1 or end == -1:
        return None
    blob = xml[start:end + len("</ownershipDocument>")]
    try:
        return ET.fromstring(blob)
    except ET.ParseError:
        return None


def _transactions_from_doc(
    doc: ET.Element, *, symbol: str, cik10: str, accession: str,
    form: str, filing_date: Optional[str], url: str,
) -> List[Dict]:
    """Extract every non-derivative + derivative transaction from one filing."""
    # rptOwnerName and issuerName are direct text (NOT <value>-wrapped).
    owner = doc.find("reportingOwner")
    insider = _text(owner, "reportingOwnerId/rptOwnerName") if owner is not None else None
    insider = insider or "Unknown"
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    role = _role(rel)
    issuer = _text(doc, "issuer/issuerName") or symbol

    rows: List[Dict] = []
    tables = [
        ("nonDerivativeTable/nonDerivativeTransaction", False),
        ("derivativeTable/derivativeTransaction", True),
    ]
    for path, is_deriv in tables:
        for txn in doc.findall(path):
            # transactionCode sits directly under transactionCoding as text (it
            # is NOT wrapped in the <value> element most Form 345 fields use).
            code = (_text(txn, "transactionCoding/transactionCode") or "").upper()
            tdate = _value(txn, "transactionDate")
            shares = _num(_value(txn, "transactionAmounts/transactionShares"))
            price = _num(_value(txn, "transactionAmounts/transactionPricePerShare"))
            ad = (_value(txn, "transactionAmounts/transactionAcquiredDisposedCode") or "").upper()
            owned_after = _num(_value(txn, "postTransactionAmounts/sharesOwnedFollowingTransaction"))
            security = _value(txn, "securityTitle")
            if shares is None and tdate is None:
                continue  # not a real, dated transaction line
            value = round(shares * price, 2) if (shares is not None and price is not None) else None
            rows.append({
                "symbol": symbol,
                "cik": cik10,
                "accession": accession,
                "insider": insider,
                "role": role,
                "issuerName": issuer,
                "code": code or None,
                "type": _CODE_TYPE.get(code, code.lower() if code else "other"),
                "acquiredDisposed": ad or None,
                "shares": shares,
                "price": price,
                "value": value,
                "sharesOwnedAfter": owned_after,
                "security": security,
                "isDerivative": is_deriv,
                "transactionDate": tdate,
                "filingDate": filing_date,
                "form": form,
                "url": url,
            })
    return rows


def fetch_insider_transactions(
    ticker: str, *, cik10: Optional[str] = None,
    since_days: int = 180, max_filings: int = 40,
) -> Dict:
    """Fetch real insider (Form 4/5) transactions for a US ticker.

    Returns ``{"symbol", "cik", "issuerName", "transactions": [...], "asOf",
    "source"}``. ``source`` is ``"live"`` whenever the EDGAR feed answered (even
    with zero recent transactions), and ``"unavailable"`` only when the ticker
    has no SEC CIK. Raises on a hard network/parse failure so the worker logs and
    skips — it never invents trades.
    """
    sym = (ticker or "").upper().strip()
    title = None
    if cik10 is None:
        hit = resolve_cik(sym)
        if not hit:
            return {"symbol": sym, "cik": None, "issuerName": None,
                    "transactions": [], "asOf": None, "source": "unavailable"}
        cik10, title = hit

    subs = fetch_submissions(cik10)
    title = title or subs.get("name") or sym
    cutoff = (date.today() - timedelta(days=since_days)).isoformat() if since_days else None

    filings = [
        f for f in _recent_filings(subs)
        if str(f.get("form", "")).split("/")[0] in _OWNERSHIP_FORMS
        and (not cutoff or (f.get("filingDate") or "") >= cutoff)
    ]
    filings = filings[:max_filings]

    transactions: List[Dict] = []
    for f in filings:
        acc = f["accession"]
        url = filing_index_url(cik10, acc)
        try:
            raw = _get(_txt_url(cik10, acc)).text
        except _resilient.CircuitOpenError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("EDGAR filing fetch failed (%s %s): %s", sym, acc, exc)
            continue
        doc = _parse_ownership_xml(raw)
        if doc is None:
            continue
        transactions.extend(_transactions_from_doc(
            doc, symbol=sym, cik10=cik10, accession=acc,
            form=str(f.get("form", "")), filing_date=f.get("filingDate"), url=url,
        ))

    transactions.sort(
        key=lambda t: (t.get("transactionDate") or "", t.get("filingDate") or ""),
        reverse=True,
    )
    as_of = max(
        [t["filingDate"] for t in transactions if t.get("filingDate")],
        default=None,
    )
    return {
        "symbol": sym,
        "cik": cik10,
        "issuerName": title,
        "transactions": transactions,
        "asOf": as_of,
        "source": "live",
    }
