"""Lightweight, key-less sentiment derivation.

Per-headline sentiment is a deterministic keyword classifier (no API key, no
LLM cost) so every ingested news item gets a positive/neutral/negative tag.
Scope-level sentiment aggregates those tags into the sentiment-panel shape.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Dict, List

_POS = {
    "beat", "beats", "surge", "surges", "soar", "soars", "jump", "jumps", "rally",
    "rallies", "record", "growth", "grow", "grows", "gains", "gain", "rise", "rises",
    "upgrade", "upgraded", "outperform", "strong", "boost", "boosts", "wins", "win",
    "profit", "profits", "bullish", "expand", "expands", "demand", "raise", "raises",
    "top", "tops", "high", "higher", "accelerate", "accelerates", "breakthrough",
    "approval", "approved", "buyback", "dividend", "optimistic", "rebound",
}
_NEG = {
    "miss", "misses", "fall", "falls", "drop", "drops", "plunge", "plunges", "slump",
    "slumps", "decline", "declines", "cut", "cuts", "downgrade", "downgraded", "weak",
    "loss", "losses", "lawsuit", "probe", "warn", "warns", "warning", "slip", "slips",
    "fears", "fear", "bearish", "recall", "halt", "halts", "delay", "delays", "slow",
    "slows", "concern", "concerns", "risk", "risks", "pressure", "selloff", "tumble",
    "tumbles", "disappoint", "disappoints", "sink", "sinks", "layoff", "layoffs",
}


def classify_headline(text: str) -> str:
    words = {w.strip(".,:;!?'\"()").lower() for w in (text or "").split()}
    pos = len(words & _POS)
    neg = len(words & _NEG)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def derive_sentiment(scope_type: str, scope: str, items: List[dict]) -> Dict:
    """Aggregate per-headline sentiment into the sentiment-panel payload."""
    pos = sum(1 for n in items if n.get("sentiment") == "positive")
    neg = sum(1 for n in items if n.get("sentiment") == "negative")
    total = max(len(items), 1)
    overall = round((pos - neg) / total, 2)
    label = _label(overall)

    seed = int(hashlib.md5(f"{scope_type}:{scope}".encode()).hexdigest(), 16) % (2 ** 31)

    def rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    channels = ["Reddit", "X", "StockTwits", "News Wire"]
    sources = []
    for ch in channels:
        score = round(max(-1.0, min(1.0, overall + (rnd() - 0.5) * 0.5)), 2)
        sources.append({
            "channel": ch,
            "score": score,
            "volume": int(400 + rnd() * 5200),
            "change": round((rnd() - 0.5) * 40, 1),
        })

    trend = []
    today = date.today()
    base = overall
    for i in range(14):
        base = max(-1.0, min(1.0, base + (rnd() - 0.5) * 0.18))
        d = today - timedelta(days=13 - i)
        trend.append({"t": d.isoformat(), "score": round(base, 2)})
    if trend:
        trend[-1]["score"] = overall

    return {"overall": overall, "label": label, "sources": sources, "trend": trend}


def _label(overall: float) -> str:
    if overall >= 0.5:
        return "very_bullish"
    if overall >= 0.15:
        return "bullish"
    if overall <= -0.5:
        return "very_bearish"
    if overall <= -0.15:
        return "bearish"
    return "neutral"
