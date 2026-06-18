"""Polymarket prediction-market adapter (key-less public APIs).

Three public, key-less Polymarket services power the prediction-market panels:

  - **Gamma API** (``gamma-api.polymarket.com``) — events + markets metadata,
    current outcome prices, volume and liquidity. Prices/outcomes/token-ids are
    returned as JSON-encoded *strings* and must be decoded.
  - **CLOB API** (``clob.polymarket.com``) — ``prices-history`` for a token, i.e.
    the yes-share price over time, which is the market's implied probability.
  - **Data API** (``data-api.polymarket.com``) — recent ``trades`` for a market
    (condition id) and a wallet's ``positions`` + portfolio ``value``.

Everything routes through the shared resilience wrapper. Functions return
normalized dicts/lists and raise / return ``None`` on failure so the skill
builders can surface a clean "unavailable" state rather than fabricating data.
The data here is real and key-less; nothing is synthesized.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from ._resilient import request as _request

_GAMMA = "https://gamma-api.polymarket.com"
_CLOB = "https://clob.polymarket.com"
_DATA = "https://data-api.polymarket.com"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AgenticTerminal/1.0)"}
_TIMEOUT = httpx.Timeout(15.0)

# Distinct breaker per host so a throttle on one Polymarket service doesn't
# needlessly cool down the others.
_SRC_GAMMA = "polymarket-gamma"
_SRC_CLOB = "polymarket-clob"
_SRC_DATA = "polymarket-data"

# Broad categories we prefer to surface, matched against an event's tag slugs
# (Gamma attaches many tags per event, finest-first; we want the broad bucket).
_CATEGORY_PRIORITY = [
    ("politics", "Politics"),
    ("elections", "Elections"),
    ("geopolitics", "Geopolitics"),
    ("crypto", "Crypto"),
    ("economy", "Economy"),
    ("business", "Business"),
    ("tech", "Tech"),
    ("science", "Science"),
    ("sports", "Sports"),
    ("pop-culture", "Culture"),
    ("culture", "Culture"),
    ("world", "World"),
]
_CATEGORY_BY_SLUG = dict(_CATEGORY_PRIORITY)


def _get_json(source: str, url: str, params: Optional[dict] = None):
    resp = _request(source, url, params=params, headers=_HEADERS,
                    timeout=_TIMEOUT, follow_redirects=True)
    return resp.json()


def _to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _json_list(v) -> list:
    """Gamma encodes outcomes/prices/clobTokenIds as JSON *strings*; decode them."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _iso(ts) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _category_of(tags) -> str:
    slugs = {(t.get("slug") or "").lower() for t in (tags or []) if isinstance(t, dict)}
    for slug, label in _CATEGORY_PRIORITY:
        if slug in slugs:
            return label
    # Fall back to the first tag's label so the event is never uncategorized.
    for t in tags or []:
        if isinstance(t, dict) and t.get("label"):
            return t["label"]
    return "Other"


def normalize_market(m: dict) -> Optional[dict]:
    """Normalize one Gamma market into a compact, decoded shape.

    Outcome prices are probabilities (0..1); ``yesProbability`` is the first
    outcome's price (the "Yes" leg for a binary market). Returns ``None`` if the
    market carries no usable identity.
    """
    if not isinstance(m, dict) or not m.get("conditionId"):
        return None
    tokens = [str(t) for t in _json_list(m.get("clobTokenIds"))]
    outcomes = [str(o) for o in _json_list(m.get("outcomes"))]
    prices = [_to_float(p) for p in _json_list(m.get("outcomePrices"))]
    yes_price = prices[0] if prices and prices[0] is not None else _to_float(m.get("lastTradePrice"))
    return {
        "id": str(m.get("id")) if m.get("id") is not None else None,
        "question": m.get("question"),
        "label": m.get("groupItemTitle") or m.get("question"),
        "slug": m.get("slug"),
        "conditionId": m.get("conditionId"),
        "tokenIds": tokens,
        "outcomes": outcomes,
        "prices": prices,
        "yesProbability": yes_price,
        "lastTradePrice": _to_float(m.get("lastTradePrice")),
        "bestBid": _to_float(m.get("bestBid")),
        "bestAsk": _to_float(m.get("bestAsk")),
        "volume": _to_float(m.get("volume")),
        "volume24hr": _to_float(m.get("volume24hr")),
        "liquidity": _to_float(m.get("liquidity")),
        "active": bool(m.get("active")),
        "closed": bool(m.get("closed")),
        "endDate": m.get("endDate"),
        "icon": m.get("icon") or m.get("image"),
    }


def normalize_event(e: dict, *, market_cap: int = 6) -> Optional[dict]:
    """Normalize a Gamma event with its child markets and a top-outcomes summary."""
    if not isinstance(e, dict) or not e.get("id"):
        return None
    markets: List[dict] = []
    for m in e.get("markets") or []:
        nm = normalize_market(m)
        if nm and (nm["active"] and not nm["closed"]):
            markets.append(nm)
    # Highest-probability outcomes first — for a binary event this is just the
    # single Yes/No market; for a multi-candidate event it's the leaders.
    ranked = sorted(
        markets,
        key=lambda x: (x["yesProbability"] if x["yesProbability"] is not None else -1),
        reverse=True,
    )
    top = [
        {"label": m["label"], "probability": m["yesProbability"],
         "marketId": m["id"], "slug": m["slug"]}
        for m in ranked[:max(1, market_cap)]
        if m["yesProbability"] is not None
    ]
    return {
        "id": str(e.get("id")),
        "slug": e.get("slug"),
        "title": (e.get("title") or "").strip(),
        "category": _category_of(e.get("tags")),
        "icon": e.get("icon") or e.get("image"),
        "volume": _to_float(e.get("volume")),
        "volume24hr": _to_float(e.get("volume24hr")),
        "liquidity": _to_float(e.get("liquidity")),
        "marketCount": len(markets),
        "endDate": e.get("endDate"),
        "topOutcomes": top,
        "markets": ranked,
    }


def fetch_events(
    category: Optional[str] = None,
    limit: int = 24,
) -> Optional[List[dict]]:
    """Top active events by 24h volume, optionally filtered by a category slug.

    Returns a list of normalized events, or ``None`` on upstream failure.
    """
    params = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": str(max(1, min(limit, 60))),
    }
    if category:
        params["tag_slug"] = category.strip().lower()
    payload = _get_json(_SRC_GAMMA, f"{_GAMMA}/events", params=params)
    if not isinstance(payload, list):
        return None
    out = [normalize_event(e) for e in payload]
    return [e for e in out if e and e["topOutcomes"]]


def fetch_market_by_slug(slug: str) -> Optional[dict]:
    payload = _get_json(_SRC_GAMMA, f"{_GAMMA}/markets", params={"slug": slug})
    rows = payload if isinstance(payload, list) else [payload]
    for m in rows:
        nm = normalize_market(m)
        if nm:
            return nm
    return None


def fetch_market_by_id(market_id: str) -> Optional[dict]:
    payload = _get_json(_SRC_GAMMA, f"{_GAMMA}/markets/{market_id}")
    m = payload[0] if isinstance(payload, list) and payload else payload
    return normalize_market(m) if isinstance(m, dict) else None


_STOPWORDS = {
    "the", "a", "an", "to", "of", "for", "in", "on", "will", "is", "be", "win",
    "market", "prediction", "polymarket", "show", "me", "odds", "probability",
    "history", "chart", "detail", "and", "vs", "by", "at", "this", "that",
}


def _relevance(text: str, query_tokens: set) -> int:
    """Count how many query tokens appear in ``text`` (case-insensitive)."""
    if not query_tokens:
        return 0
    low = (text or "").lower()
    return sum(1 for t in query_tokens if t in low)


def search_market(query: str) -> Optional[dict]:
    """Resolve a free-text query to the single best-matching active market.

    Uses Gamma's public-search (events with nested markets) and ranks candidates
    by query-token relevance first (so "Spain win World Cup" picks the Spain
    market, not the highest-volume sibling), then by traded volume as a
    tiebreaker. Returns ``None`` when nothing matches.
    """
    payload = _get_json(
        _SRC_GAMMA, f"{_GAMMA}/public-search",
        params={"q": query, "limit_per_type": "10", "events_status": "active"},
    )
    events = payload.get("events") if isinstance(payload, dict) else None
    q_tokens = {t for t in (query or "").lower().split() if t not in _STOPWORDS and len(t) > 1}

    best: Optional[dict] = None
    best_key: tuple = (-1, -1.0)
    for e in events or []:
        for m in e.get("markets") or []:
            nm = normalize_market(m)
            if not nm or nm["closed"] or not nm["active"]:
                continue
            # Score against both the market question and its short label so that
            # multi-outcome events resolve to the specific candidate asked for.
            rel = max(
                _relevance(nm.get("question") or "", q_tokens),
                _relevance(nm.get("label") or "", q_tokens),
            )
            vol = nm["volume24hr"] or nm["volume"] or 0.0
            key = (rel, vol)
            if key > best_key:
                best, best_key = nm, key
    return best


# Default sampling resolution (minutes per point) per CLOB range. The CLOB
# rejects some ranges without an explicit ``fidelity`` (e.g. "1m" requires >=10),
# so we always send a sensible default sized to the window.
_FIDELITY_BY_INTERVAL = {
    "1h": 1,
    "6h": 5,
    "1d": 15,
    "1w": 60,
    "1m": 180,
    "max": 720,
}


def fetch_price_history(
    token_id: str,
    interval: str = "1m",
    fidelity: Optional[int] = None,
) -> Optional[dict]:
    """Yes-share price history for a CLOB token = implied probability over time.

    ``interval`` is a CLOB range token (1h/6h/1d/1w/1m/max). Returns
    ``{"points": [{"t": iso, "p": price, "prob": pct}], "interval", "asOf"}`` or
    ``None`` when no usable history comes back.
    """
    fid = fidelity or _FIDELITY_BY_INTERVAL.get(interval, 60)
    params: Dict[str, str] = {
        "market": token_id, "interval": interval, "fidelity": str(fid),
    }
    payload = _get_json(_SRC_CLOB, f"{_CLOB}/prices-history", params=params)
    history = payload.get("history") if isinstance(payload, dict) else None
    if not history:
        return None
    points: List[dict] = []
    for row in history:
        p = _to_float(row.get("p"))
        t = row.get("t")
        if p is None or t is None:
            continue
        points.append({
            "t": _iso(t),
            "p": round(p, 4),
            "prob": round(p * 100.0, 1),
        })
    if not points:
        return None
    return {"points": points, "interval": interval, "asOf": points[-1]["t"]}


def fetch_trades(condition_id: str, limit: int = 40) -> Optional[List[dict]]:
    """Recent trades for a market (by condition id), newest first.

    Returns normalized trade prints, or ``None`` on failure. An empty list means
    the market simply has no recent trades.
    """
    payload = _get_json(
        _SRC_DATA, f"{_DATA}/trades",
        params={"market": condition_id, "limit": str(max(1, min(limit, 100))),
                "takerOnly": "false"},
    )
    if not isinstance(payload, list):
        return None
    out: List[dict] = []
    for t in payload:
        price = _to_float(t.get("price"))
        size = _to_float(t.get("size"))
        if price is None or size is None:
            continue
        out.append({
            "time": _iso(t.get("timestamp")),
            "side": (t.get("side") or "").upper(),
            "price": round(price, 4),
            "size": round(size, 2),
            "usd": round(price * size, 2),
            "outcome": t.get("outcome"),
            "wallet": t.get("proxyWallet"),
        })
    return out


def fetch_wallet(address: str) -> Optional[dict]:
    """A wallet's open Polymarket positions plus aggregate portfolio value.

    Returns ``{"address", "positions": [...], "value", "asOf"}`` or ``None`` if
    positions cannot be fetched. ``value`` is the current mark of open positions
    (USD) from the data API.
    """
    addr = (address or "").strip().lower()
    if not addr:
        return None
    pos_payload = _get_json(
        _SRC_DATA, f"{_DATA}/positions",
        params={"user": addr, "limit": "50", "sortBy": "CURRENT",
                "sortDirection": "DESC"},
    )
    if not isinstance(pos_payload, list):
        return None
    positions: List[dict] = []
    for p in pos_payload:
        positions.append({
            "title": p.get("title"),
            "outcome": p.get("outcome"),
            "slug": p.get("slug"),
            "icon": p.get("icon"),
            "size": _to_float(p.get("size")),
            "avgPrice": _to_float(p.get("avgPrice")),
            "curPrice": _to_float(p.get("curPrice")),
            "initialValue": _to_float(p.get("initialValue")),
            "currentValue": _to_float(p.get("currentValue")),
            "cashPnl": _to_float(p.get("cashPnl")),
            "percentPnl": _to_float(p.get("percentPnl")),
            "realizedPnl": _to_float(p.get("realizedPnl")),
            "redeemable": bool(p.get("redeemable")),
            "endDate": p.get("endDate"),
        })

    value = None
    try:
        val_payload = _get_json(_SRC_DATA, f"{_DATA}/value", params={"user": addr})
        if isinstance(val_payload, list) and val_payload:
            value = _to_float(val_payload[0].get("value"))
        elif isinstance(val_payload, dict):
            value = _to_float(val_payload.get("value"))
    except Exception:
        value = None

    return {
        "address": addr,
        "positions": positions,
        "value": value,
        "asOf": datetime.now(tz=timezone.utc).isoformat(),
    }
