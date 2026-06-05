"""Key-less news adapters.

Three free, key-less feeds, all normalized into the news schema and tagged with
a deterministic keyword sentiment:

  - Yahoo per-ticker RSS  (``fetch_news``)     — headlines for one or more tickers.
  - Google News RSS search(``fetch_topic_news``) — free-text/topic headline search.
  - Google News business  (``fetch_market_news``) — broad market headlines.

Every fetcher returns a list of normalized items. ``dedupe`` collapses overlap
across sources by URL/title so the same story isn't shown twice.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import feedparser
import httpx

from .sentiment import classify_headline

_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline"
_GOOGLE_SEARCH = "https://news.google.com/rss/search"
_GOOGLE_BUSINESS = "https://news.google.com/rss/headlines/section/topic/BUSINESS"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AgenticTerminal/1.0)"}
_TIMEOUT = httpx.Timeout(12.0)


def fetch_news(
    symbols: List[str],
    sector: Optional[str] = None,
    limit: int = 20,
    timeout: Optional[float] = None,
) -> List[Dict]:
    """Fetch and normalize Yahoo RSS news for one or more symbols. Raises on network error."""
    syms = [s.upper() for s in symbols if s]
    if not syms:
        return []
    params = {"s": ",".join(syms), "region": "US", "lang": "en-US"}
    feed = _get_feed(_RSS, params=params, timeout=timeout)
    items: List[Dict] = []
    for entry in feed.entries[:limit]:
        item = _normalize(entry, fallback_tickers=syms, sector=sector,
                           default_source="Yahoo Finance")
        if item:
            items.append(item)
    return items


def fetch_topic_news(
    query: str,
    limit: int = 30,
    timeout: Optional[float] = None,
) -> List[Dict]:
    """Free-text/topic headline search via Google News RSS. Raises on network error."""
    q = (query or "").strip()
    if not q:
        return []
    url = f"{_GOOGLE_SEARCH}?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
    feed = _get_feed(url, timeout=timeout)
    items: List[Dict] = []
    for entry in feed.entries[:limit]:
        item = _normalize(entry, fallback_tickers=[], sector=None,
                          default_source="Google News")
        if item:
            items.append(item)
    return items


def fetch_market_news(limit: int = 30, timeout: Optional[float] = None) -> List[Dict]:
    """Broad market/business headlines via Google News RSS. Raises on network error."""
    url = f"{_GOOGLE_BUSINESS}?hl=en-US&gl=US&ceid=US:en"
    feed = _get_feed(url, timeout=timeout)
    items: List[Dict] = []
    for entry in feed.entries[:limit]:
        item = _normalize(entry, fallback_tickers=[], sector=None,
                          default_source="Google News")
        if item:
            items.append(item)
    return items


def dedupe(items: List[Dict]) -> List[Dict]:
    """Collapse duplicate stories across sources by URL then normalized title."""
    seen_urls: set = set()
    seen_titles: set = set()
    out: List[Dict] = []
    for it in items:
        url = (it.get("url") or "").split("?", 1)[0].rstrip("/").lower()
        title_key = re.sub(r"[^a-z0-9]+", " ", (it.get("headline") or "").lower()).strip()
        if url and url in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)
        out.append(it)
    return out


# ----------------------------- internals -----------------------------
def _get_feed(url: str, params: Optional[dict] = None, timeout: Optional[float] = None):
    to = httpx.Timeout(timeout) if timeout is not None else _TIMEOUT
    with httpx.Client(timeout=to, headers=_HEADERS, follow_redirects=True) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return feedparser.parse(resp.content)


def _normalize(entry, fallback_tickers: List[str], sector: Optional[str],
               default_source: str) -> Optional[Dict]:
    headline = (entry.get("title") or "").strip()
    if not headline:
        return None
    url = entry.get("link") or None
    summary = _clean(entry.get("summary") or "")
    published = _parse_date(entry.get("published") or entry.get("updated"))
    tickers = _entry_tickers(entry, fallback_tickers)
    # Google News puts the publisher after a trailing " - Publisher" in the title
    # and as entry.source; prefer that, else derive from the link host.
    source = _entry_source(entry) or _source_of(url) or default_source
    headline = _strip_publisher_suffix(headline)
    return {
        "id": _stable_id(url or headline),
        "headline": headline,
        "source": source,
        "summary": summary or headline,
        "url": url,
        "publishedAt": published,
        "sentiment": classify_headline(headline + " " + summary),
        "tickers": tickers,
        "sector": sector,
    }


def _entry_source(entry) -> Optional[str]:
    src = entry.get("source")
    if isinstance(src, dict):
        title = src.get("title")
        if title:
            return title.strip()
    title = entry.get("title") or ""
    if " - " in title:
        tail = title.rsplit(" - ", 1)[-1].strip()
        if 0 < len(tail) <= 40:
            return tail
    return None


def _strip_publisher_suffix(headline: str) -> str:
    if " - " in headline:
        head, tail = headline.rsplit(" - ", 1)
        if 0 < len(tail) <= 40 and head.strip():
            return head.strip()
    return headline


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
        if host.startswith("news.google"):
            return None
        return host.split(".")[0].capitalize()
    except Exception:
        return None


def _clean(text: str) -> str:
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
