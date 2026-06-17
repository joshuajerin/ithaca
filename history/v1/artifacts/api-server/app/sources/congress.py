"""Key-less U.S. congressional trading disclosure adapter.

Members of Congress must publicly disclose their securities transactions under
the STOCK Act (House Periodic Transaction Reports + Senate Financial
Disclosures). Those filings are public but live in awkward formats (House PTR
PDFs, the Senate eFD search behind a session form). This adapter reads the free,
key-less ``beta/live/congresstrading`` feed published by Quiver Quantitative,
which parses the official House/Senate filings into JSON, and normalizes the
most recent disclosures into the congress-trade schema.

The data is the legally-required *public* disclosure; Quiver is the free
aggregator. There is a real reporting lag between when a member trades and when
it must be disclosed (up to ~45 days under the STOCK Act), so each record's
``transactionDate`` and ``disclosureDate`` differ — the panel surfaces that lag
honestly rather than implying real-time visibility.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Dict, List, Optional

import httpx

from ._resilient import request as _request

_ENDPOINT = "https://api.quiverquant.com/beta/live/congresstrading"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AgenticTerminal/1.0)",
    "Accept": "application/json",
}
_TIMEOUT = httpx.Timeout(15.0)
_SOURCE = "quiver-congress"

_PARTY = {"D": "Democrat", "R": "Republican", "I": "Independent"}
_RANGE_NUM = re.compile(r"\$?\s*([\d,]+)")


def _norm_type(raw: str) -> str:
    """Map the disclosed transaction label to a buy/sell/exchange bucket."""
    r = (raw or "").strip().lower()
    if "purchase" in r or r == "buy":
        return "buy"
    if "sale" in r or "sell" in r or "sold" in r:
        return "sell"
    if "exchange" in r:
        return "exchange"
    return "other"


def _parse_range(rng: str):
    """Pull the low/high dollar bounds out of a '$1,001 - $15,000' range string."""
    if not rng:
        return None, None
    nums = [int(m.replace(",", "")) for m in _RANGE_NUM.findall(rng)]
    if not nums:
        return None, None
    low = float(nums[0])
    high = float(nums[1]) if len(nums) > 1 else low
    return low, high


def _norm_date(value) -> Optional[str]:
    """Coerce a feed date to an ISO yyyy-mm-dd string, or None if unparseable."""
    if not value:
        return None
    s = str(value).strip()[:10]
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return None


def _lag_days(txn: Optional[str], disc: Optional[str]) -> Optional[int]:
    if not txn or not disc:
        return None
    try:
        d = (date.fromisoformat(disc) - date.fromisoformat(txn)).days
    except ValueError:
        return None
    return d if d >= 0 else None


def _stable_id(member: str, ticker: Optional[str], txn_date: Optional[str],
               raw_type: str, rng: Optional[str]) -> str:
    key = "|".join([member or "", ticker or "", txn_date or "", raw_type or "", rng or ""])
    return "ct-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _politician_url(name: str) -> Optional[str]:
    """Best-effort link to the member's public disclosure page (the aggregator's
    per-politician view of the underlying filings). Per-transaction filing links
    are not present in this feed, so this is the most specific source we can give."""
    if not name:
        return None
    from urllib.parse import quote
    return f"https://www.quiverquant.com/congresstrading/politician/{quote(name.strip())}"


def fetch_congress_trades(limit: int = 1000,
                          timeout: Optional[float] = None) -> List[Dict]:
    """Fetch + normalize the most recent disclosed congressional trades.

    Raises on network error / throttle so callers fall back to whatever is
    already stored (or the curated mock set)."""
    to = httpx.Timeout(timeout) if timeout else _TIMEOUT
    resp = _request(_SOURCE, _ENDPOINT, headers=_HEADERS, timeout=to)
    payload = resp.json()
    if not isinstance(payload, list):
        return []
    out: List[Dict] = []
    for rec in payload[:limit]:
        member = (rec.get("Representative") or "").strip()
        if not member:
            continue
        ticker = (rec.get("Ticker") or "").strip().upper() or None
        raw_type = (rec.get("Transaction") or "").strip()
        rng = (rec.get("Range") or "").strip() or None
        txn_date = _norm_date(rec.get("TransactionDate"))
        disc_date = _norm_date(rec.get("ReportDate"))
        chamber = "Senate" if (rec.get("House") or "").strip().lower().startswith("sen") else "House"
        party_code = (rec.get("Party") or "").strip().upper() or None
        low, high = _parse_range(rng)
        out.append({
            "id": _stable_id(member, ticker, txn_date, raw_type, rng),
            "member": member,
            "chamber": chamber,
            "party": _PARTY.get(party_code or "", "Unknown"),
            "partyCode": party_code,
            "ticker": ticker,
            "type": _norm_type(raw_type),
            "rawType": raw_type or None,
            "amountRange": rng,
            "amountLow": low,
            "amountHigh": high,
            "transactionDate": txn_date,
            "disclosureDate": disc_date,
            "lagDays": _lag_days(txn_date, disc_date),
            "sourceUrl": _politician_url(member),
            "description": (rec.get("Description") or None),
        })
    return out


def dedupe(items: List[Dict]) -> List[Dict]:
    """Collapse duplicate disclosures by their stable id."""
    seen: set = set()
    out: List[Dict] = []
    for it in items:
        k = it.get("id")
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out
