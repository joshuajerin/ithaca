"""News adapter using Yahoo Finance's key-less per-ticker RSS feed.

`https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbols}` returns recent
headlines for one or more tickers. We normalize into the news schema and tag
each item with a deterministic keyword sentiment.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import feedparser
import httpx

from .sentiment import classify_headline

_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AgenticTerminal/1.0)"}
_TIMEOUT = httpx.Timeout(12.0)


def fetch_news(symbols: List[str], sector: Optional[str] = None, limit: int = 20) -> List[Dict]:
    """Fetch and normalize news for one or more symbols. Raises on network error."""
    syms = [s.upper() for s in symbols if s]
    if not syms:
        return []
    params = {"s": ",".join(syms), "region": "US", "lang": "en-US"}
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
        resp = client.get(_RSS, params=params)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

    items: List[Dict] = []
    for entry in feed.entries[:limit]:
        headline = (entry.get("title") or "").strip()
        if not headline:
            continue
        url = entry.get("link") or None
        summary = _clean(entry.get("summary") or "")
        published = _parse_date(entry.get("published") or entry.get("updated"))
        tickers = _entry_tickers(entry, syms)
        items.append({
            "id": _stable_id(url or headline),
            "headline": headline,
            "source": _source_of(url) or "Yahoo Finance",
            "summary": summary or headline,
            "url": url,
            "publishedAt": published,
            "sentiment": classify_headline(headline + " " + summary),
            "tickers": tickers,
            "sector": sector,
        })
    return items


def _entry_tickers(entry, fallback: List[str]) -> List[str]:
    tags = entry.get("tags") or []
    found = [t.get("term", "").upper() for t in tags if t.get("term")]
    found = [t for t in found if t.isalpha() and 1 <= len(t) <= 6]
    return found or fallback


def _stable_id(seed: str) -> str:
    return "news-" + hashlib.sha1(seed.encode()).hexdigest()[:16]


def _source_of(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        host = url.split("//", 1)[-1].split("/", 1)[0]
        host = host.replace("www.", "")
        return host.split(".")[0].capitalize()
    except Exception:
        return None


def _clean(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text).strip()[:400]


def _parse_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None
