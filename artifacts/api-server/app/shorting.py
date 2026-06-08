"""Shorting desk assembly: turn a book into honest borrow / financing / margin.

This is the *assembly* layer over the pure ``engine.borrow`` engine. It owns the
two real-world inputs the engine deliberately doesn't fetch:

- **Liquidity** — each name's 20-day dollar ADV (price × volume) and market cap,
  read from the company repo, which drives the borrow-tier classification.
- **Financing anchor** — a real short-tenor reference rate. We read the 3-month
  point off the live U.S. Treasury par-yield curve as the GC anchor; if that
  fetch is unavailable we fall back to a clearly-labeled assumed rate and report
  ``source="mock"`` rather than inventing a live number.

``build`` produces the ``shorting_desk`` panel payload: the resolved long/short
book, a per-name borrow table (tier, fee, shortable, $ cost), the carrying-cost
breakdown, and the Reg-T margin / leverage / breach profile. Names that are
locate-infeasible are flagged and, when the book was *constructed* here (not
supplied with explicit weights), dropped from the short side with a note.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from . import repo
from .engine import borrow
from .sources import rates

# Documented fallback GC anchor used only when the live Treasury fetch fails.
# Chosen to sit in a plausible short-rate range; always reported as mock.
_FALLBACK_GC_PCT = 4.5
_DEFAULT_CAPITAL = 1_000_000.0
_MAX_NAMES = 24


def financing_anchor() -> Tuple[float, str, Optional[str]]:
    """Return (gc_rate_pct, source, asOf) — the GC financing anchor.

    Uses the 3-month point of the live Treasury par-yield curve. Falls back to a
    labeled assumed rate (source="mock") when the live curve is unavailable.
    """
    try:
        curve = rates.fetch_treasury_curve()
    except Exception:
        curve = None
    if curve and curve.get("tenors"):
        gc = rates.interp_treasury(curve["tenors"], 0.25)
        if gc is not None:
            return round(float(gc), 3), "live", curve.get("asOf")
    return _FALLBACK_GC_PCT, "mock", None


def borrow_profile(symbols: List[str]) -> Dict[str, dict]:
    """Classify the borrow profile of each symbol from its real liquidity.

    Returns ``{symbol: {tier, label, feeBps, shortable, note, dollarAdv,
    marketCap, source}}``. Names the repo cannot resolve are omitted.
    """
    syms = [s.upper() for s in symbols if s]
    companies = repo.companies_bulk(syms)
    out: Dict[str, dict] = {}
    for s in syms:
        c = companies.get(s)
        if not c:
            continue
        price = float(c.get("price") or 0.0)
        volume = float(c.get("volume") or 0.0)
        mcap = float(c.get("marketCap") or 0.0)
        dollar_adv = price * volume
        prof = borrow.classify_borrow(dollar_adv, mcap)
        prof["dollarAdv"] = round(dollar_adv, 2)
        prof["marketCap"] = round(mcap, 2)
        prof["source"] = c.get("_source", "mock")
        prof["asOf"] = c.get("_asOf")
        out[s] = prof
    return out


def _resolve_book(params: dict) -> Tuple[List[Tuple[str, float]], str]:
    """Resolve a list of (symbol, signed_weight) plus a human label.

    Three ways to specify the book, in priority order:
    1. ``weights``: an explicit ``{symbol: signed_weight}`` map.
    2. ``longs`` / ``shorts``: name lists -> equal-weight dollar-neutral book.
    3. ``symbols``: split by 1-day change into a dollar-neutral momentum book
       (recent winners long, losers short). Falls back to a default core book.
    """
    weights = params.get("weights")
    if isinstance(weights, dict) and weights:
        book = [(s.upper(), float(w)) for s, w in weights.items() if repo.get_company(s.upper())]
        return book[:_MAX_NAMES], "custom weighted book"

    longs = [s.upper() for s in (params.get("longs") or []) if repo.get_company(s.upper())]
    shorts = [s.upper() for s in (params.get("shorts") or []) if repo.get_company(s.upper())]
    if longs or shorts:
        book: List[Tuple[str, float]] = []
        lw = 0.5 / len(longs) if longs else 0.0
        sw = 0.5 / len(shorts) if shorts else 0.0
        book += [(s, lw) for s in longs]
        book += [(s, -sw) for s in shorts]
        return book[:_MAX_NAMES], f"{len(longs)} long / {len(shorts)} short"

    syms = [s.upper() for s in (params.get("symbols") or []) if repo.get_company(s.upper())]
    if len(syms) < 2:
        syms = ["NVDA", "MSFT", "GOOGL", "META", "AMZN", "AAPL", "TSLA", "AMD"]
    companies = repo.companies_bulk(syms)
    ranked = sorted(syms, key=lambda s: float((companies.get(s) or {}).get("changePct") or 0.0),
                    reverse=True)
    half = max(1, len(ranked) // 2)
    longs = ranked[:half]
    shorts = ranked[-half:]
    # Avoid a name appearing on both sides for odd counts.
    shorts = [s for s in shorts if s not in longs]
    lw = 0.5 / len(longs) if longs else 0.0
    sw = 0.5 / len(shorts) if shorts else 0.0
    book = [(s, lw) for s in longs] + [(s, -sw) for s in shorts]
    return book[:_MAX_NAMES], "momentum-ranked dollar-neutral book"


def build(params: dict) -> dict:
    """Build the ``shorting_desk`` panel payload for a long/short book.

    ``params`` accepts ``weights`` | ``longs``/``shorts`` | ``symbols`` to define
    the book and an optional ``capital`` (default $1M). Returns the resolved book
    with per-name borrow detail, the carrying-cost breakdown, and the Reg-T
    margin / leverage / breach profile, with honest source/asOf provenance.
    """
    capital = float(params.get("capital") or _DEFAULT_CAPITAL)
    book, label = _resolve_book(params)
    book_syms = [s for s, _ in book]
    profile = borrow_profile(book_syms)
    gc_pct, fin_source, fin_asof = financing_anchor()

    # Drop locate-infeasible names from the SHORT side only when this desk built
    # the book itself (no explicit weights). Honor explicit shorts but flag them.
    explicit = isinstance(params.get("weights"), dict) and params["weights"]
    holdings: List[dict] = []
    blocked: List[str] = []
    short_legs: List[dict] = []
    long_mv = 0.0
    short_mv = 0.0
    for sym, w in book:
        prof = profile.get(sym, {})
        shortable = bool(prof.get("shortable", True))
        side = "long" if w >= 0 else "short"
        mv = abs(w) * capital
        if side == "short" and not shortable:
            blocked.append(sym)
            if not explicit:
                # Skip the position entirely; it can't be put on.
                continue
        if side == "long":
            long_mv += mv
        else:
            short_mv += mv
            short_legs.append({"symbol": sym, "mv": mv, "feeBps": prof.get("feeBps", 0.0)})
        holdings.append({
            "symbol": sym,
            "name": (repo.get_company(sym) or {}).get("name", sym),
            "side": side,
            "weight": round(w, 4),
            "marketValue": round(mv, 2),
            "tier": prof.get("tier"),
            "tierLabel": prof.get("label"),
            "feeBps": prof.get("feeBps"),
            "shortable": shortable,
            "borrowCostAnnual": round(mv * float(prof.get("feeBps") or 0.0) / 10000.0, 2)
            if side == "short" else 0.0,
            "dollarAdv": prof.get("dollarAdv"),
            "note": prof.get("note") or "",
        })

    holdings.sort(key=lambda h: (h["side"] != "short", -h["marketValue"]))
    nav = capital
    cash = borrow.book_cash(capital, long_mv, short_mv)
    carry = borrow.carry_breakdown(short_legs, cash, nav, gc_pct)
    margin = borrow.margin_profile(long_mv, short_mv, capital)

    notes: List[str] = []
    if blocked:
        if explicit:
            notes.append(
                "Locate-infeasible (cannot be borrowed): "
                + ", ".join(blocked) + " — shown but not realistically shortable."
            )
        else:
            notes.append(
                "Dropped from the short side (locate-infeasible): " + ", ".join(blocked) + "."
            )
    htb = [h["symbol"] for h in holdings if h["side"] == "short" and h.get("tier") == "htb"]
    if htb:
        notes.append("Hard-to-borrow shorts (elevated, volatile fees): " + ", ".join(htb) + ".")
    if margin["breach"]:
        notes.extend(margin["warnings"])

    # Provenance: live only when both the prices and the financing rate are live.
    price_sources = {p.get("source", "mock") for p in profile.values()} or {"mock"}
    as_ofs = [p.get("asOf") for p in profile.values() if p.get("asOf")]
    source = "live" if (price_sources == {"live"} and fin_source == "live") else "mock"
    as_of = max(as_ofs) if as_ofs else fin_asof

    return {
        "label": label,
        "capital": round(capital, 2),
        "holdings": holdings,
        "longCount": sum(1 for h in holdings if h["side"] == "long"),
        "shortCount": sum(1 for h in holdings if h["side"] == "short"),
        "carry": carry,
        "margin": margin,
        "financing": {
            "gcRatePct": gc_pct,
            "anchor": "3M U.S. Treasury par yield",
            "source": fin_source,
            "asOf": fin_asof,
        },
        "blocked": blocked,
        "notes": notes,
        "assumptions": (
            "Borrow fees are a liquidity-keyed model (no live locate feed); financing "
            "anchored to the 3M Treasury bill + 50bps, cash rebate at GC − 35bps. "
            "Margin follows Reg-T (50% initial, 25%/30% long/short maintenance)."
        ),
        "asOf": as_of,
        "source": source,
    }
