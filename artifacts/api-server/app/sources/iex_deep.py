"""Real intraday order-book reconstruction from IEX Exchange HIST DEEP captures.

IEX publishes its full historical market-data feeds (the same binary the live
feed carries) as downloadable pcap captures the morning after each trading
session — true T+1. The DEEP feed carries aggregated depth-of-book: one message
per price-level change plus every trade report, for every symbol IEX traded that
day. By replaying it we can rebuild a *real* depth ladder + tape for any symbol,
labelled honestly as venue-only (IEX prints, not the consolidated tape).

Why parse the wire format by hand instead of a library:
  - The published files are huge (a single DEEP day is ~13 GB gzipped). We must
    stream the gzip and decode messages incrementally, filtering to just the
    requested symbol(s) so memory stays bounded — a parser that insists on the
    whole file on disk is unusable here.
  - The format is small and stable, so a direct ``struct`` decoder needs no
    third-party dependency (and dodges the package firewall).

Wire format (decoded top-down):
  - File container: **pcapng** (NOT classic pcap). Magic ``0x0A0D0D0A`` (Section
    Header Block). The SHB byte-order magic ``0x1A2B3C4D`` fixes endianness.
    Blocks: SHB / IDB(0x1) / Enhanced-Packet(0x6) / Simple-Packet(0x3). Packet
    bytes live inside EPB/SPB. Link type is Ethernet II (1).
  - Each captured packet: Ethernet(14) + IPv4 + UDP, then one **IEX-TP** segment.
  - IEX-TP segment header (40 bytes): byte0 version (0x01); bytes[2:4] LE message
    protocol id (DEEP = ``0x8004``); [16:18] LE payload length; [18:20] LE message
    count; messages start at offset 40, each framed as ``LE uint16 length`` + body.
  - DEEP message body: byte0 type (``'8'`` buy price level, ``'5'`` sell price
    level, ``'T'`` trade report); [2:10] LE int64 timestamp (ns since epoch);
    [10:18] 8-byte space-padded symbol; [18:22] LE uint32 size; [22:30] LE int64
    price in 1/10000 dollars. A price-level update with size 0 removes that level.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import struct
import threading
import time
import zlib
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import httpx

from . import _resilient

log = logging.getLogger("terminal.sources.iex_deep")

HIST_URL = "https://iextrading.com/api/1.0/hist"
_NY = ZoneInfo("America/New_York")

# Regular trading session in minutes-of-day (ET): 09:30 -> 16:00.
SESSION_START = 570
SESSION_END = 960
FRAME_STEP = 10
FRAME_MINUTES: List[int] = list(range(SESSION_START, SESSION_END + 1, FRAME_STEP))

LEVELS = 8          # depth ladder levels per side shown in the panel
TAPE_LEN = 18       # trailing prints carried on each frame
TAPE_BUFFER = 64    # rolling raw tape kept in memory per symbol
MIN_FRAMES = 2      # below this we treat the symbol as having no real depth

# DEEP message type bytes.
_BUY = 0x38   # '8'  price level update, buy side
_SELL = 0x35  # '5'  price level update, sell side
_TRADE = 0x54 # 'T'  trade report
_PRICE_DIV = 10000.0

_DEEP_PROTO = 0x8004


# --------------------------------------------------------------------------- #
# HIST listing
# --------------------------------------------------------------------------- #
def list_deep_sessions() -> List[dict]:
    """Return every available DEEP 1.0 session as ``{date, link, size}``, oldest
    first. Raises on network/throttle failure (callers treat that as "no data")."""
    resp = _resilient.request(
        "iex_hist", HIST_URL,
        timeout=httpx.Timeout(connect=15.0, read=60.0, write=60.0, pool=60.0),
        follow_redirects=True,
    )
    listing = resp.json()
    out: List[dict] = []
    for date_key, entries in listing.items():
        for e in entries or []:
            if e.get("feed") == "DEEP":
                out.append({"date": date_key, "link": e.get("link"), "size": e.get("size")})
                break
    out.sort(key=lambda r: r["date"])
    return out


_latest_cache: Optional[Tuple[str, str]] = None
_latest_cache_at: float = 0.0
_latest_lock = threading.Lock()
_LATEST_TTL = 3600.0  # the day's file appears once; an hour of caching is plenty


def latest_session() -> Optional[Tuple[str, str]]:
    """Most recent DEEP session as ``(iso_date, download_link)``, cached.

    ``iso_date`` is ``YYYY-MM-DD``; the raw HIST key is ``YYYYMMDD``."""
    global _latest_cache, _latest_cache_at
    with _latest_lock:
        if _latest_cache and (time.monotonic() - _latest_cache_at) < _LATEST_TTL:
            return _latest_cache
    try:
        sessions = list_deep_sessions()
    except Exception as exc:  # noqa: BLE001
        log.warning("could not list IEX HIST DEEP sessions: %s", exc)
        return None
    if not sessions:
        return None
    last = sessions[-1]
    raw = last["date"]
    iso = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    result = (iso, last["link"])
    with _latest_lock:
        _latest_cache = result
        _latest_cache_at = time.monotonic()
    return result


def latest_session_date() -> Optional[str]:
    s = latest_session()
    return s[0] if s else None


# --------------------------------------------------------------------------- #
# Binary parsing
# --------------------------------------------------------------------------- #
def _parse_packet(pkt: bytes, symbols: Optional[Set[bytes]]):
    """Yield ``(mtype, ts_ns, symbol_bytes, size, price_raw)`` for the DEEP
    price-level / trade messages in one captured packet, filtered to ``symbols``
    (8-byte space-padded keys) when given."""
    if len(pkt) < 42:
        return
    ethertype = (pkt[12] << 8) | pkt[13]
    off = 14
    if ethertype == 0x8100:  # 802.1Q VLAN tag
        ethertype = (pkt[16] << 8) | pkt[17]
        off = 18
    if ethertype != 0x0800:  # not IPv4
        return
    if pkt[off + 9] != 17:   # not UDP
        return
    ihl = (pkt[off] & 0x0F) * 4
    seg = pkt[off + ihl + 8:]
    if len(seg) < 40 or seg[0] != 0x01:
        return
    if (seg[2] | (seg[3] << 8)) != _DEEP_PROTO:
        return
    plen = seg[16] | (seg[17] << 8)
    moff = 40
    end = min(len(seg), 40 + plen)
    while moff + 2 <= end:
        mlen = seg[moff] | (seg[moff + 1] << 8)
        if mlen == 0:
            break
        body = seg[moff + 2:moff + 2 + mlen]
        moff += 2 + mlen
        if len(body) < 30:
            continue
        mtype = body[0]
        if mtype != _BUY and mtype != _SELL and mtype != _TRADE:
            continue
        sym = body[10:18]
        if symbols is not None and sym not in symbols:
            continue
        ts_ns = struct.unpack_from("<q", body, 2)[0]
        size = struct.unpack_from("<I", body, 18)[0]
        price_raw = struct.unpack_from("<q", body, 22)[0]
        yield mtype, ts_ns, sym, size, price_raw


def iter_deep_messages(
    chunks: Iterable[bytes],
    symbols: Optional[Set[str]] = None,
) -> Iterator[Tuple[int, int, str, int, int]]:
    """Stream-decode DEEP messages from an iterable of **decompressed** pcapng
    byte chunks. Yields ``(mtype, ts_ns, symbol, size, price_raw)``.

    Stateful across chunk boundaries: it buffers a partial pcapng block until the
    whole block has arrived, so callers can feed arbitrary network-sized chunks.
    """
    sym_keys: Optional[Set[bytes]] = None
    if symbols is not None:
        sym_keys = {s.upper().encode("ascii").ljust(8)[:8] for s in symbols}

    buf = bytearray()
    le = "<"  # endianness, locked from the Section Header Block

    for chunk in chunks:
        buf.extend(chunk)
        while True:
            if len(buf) < 12:
                break
            btype = struct.unpack_from("<I", buf, 0)[0]
            if btype == 0x0A0D0D0A:  # SHB carries its own byte-order magic
                bom = struct.unpack_from("<I", buf, 8)[0]
                le_local = "<" if bom == 0x1A2B3C4D else ">"
                tlen = struct.unpack_from(le_local + "I", buf, 4)[0]
            else:
                tlen = struct.unpack_from(le + "I", buf, 4)[0]
            if tlen < 12 or tlen > 67_108_864:  # 64 MB sanity cap
                raise ValueError(f"bad pcapng block length {tlen} (type {btype:#x})")
            if len(buf) < tlen:
                break
            block = bytes(buf[:tlen])
            del buf[:tlen]

            if btype == 0x0A0D0D0A:
                bom = struct.unpack_from("<I", block, 8)[0]
                le = "<" if bom == 0x1A2B3C4D else ">"
            elif btype == 0x00000006:  # Enhanced Packet Block
                caplen = struct.unpack_from(le + "I", block, 20)[0]
                pkt = block[28:28 + caplen]
                for m in _parse_packet(pkt, sym_keys):
                    mt, ts, sb, sz, pr = m
                    yield mt, ts, sb.rstrip(b" ").decode("ascii", "replace"), sz, pr
            elif btype == 0x00000003:  # Simple Packet Block
                origlen = struct.unpack_from(le + "I", block, 8)[0]
                pkt = block[12:12 + origlen]
                for m in _parse_packet(pkt, sym_keys):
                    mt, ts, sb, sz, pr = m
                    yield mt, ts, sb.rstrip(b" ").decode("ascii", "replace"), sz, pr
            # IDB (0x1) and other block types carry no DEEP messages.


# --------------------------------------------------------------------------- #
# Reconstruction
# --------------------------------------------------------------------------- #
def _et_offset_seconds(session_iso: str) -> int:
    """UTC->ET offset (seconds) for the session date. Constant within an RTH
    session, so we compute it once and apply it to every nanosecond timestamp
    with cheap integer math instead of per-message tz conversion."""
    d = _dt.date.fromisoformat(session_iso)
    noon = _dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=_NY)
    return int(noon.utcoffset().total_seconds())


class _SymbolBook:
    """Running depth-of-book + tape for one symbol, snapshotting frames as the
    session clock crosses each cadence boundary."""

    def __init__(self, symbol: str, name: str, block_threshold: float) -> None:
        self.symbol = symbol
        self.name = name
        self.block_threshold = max(block_threshold, 100.0)
        self.sweep_threshold = self.block_threshold * 0.4
        self.bids: Dict[int, int] = {}   # price_raw -> size
        self.asks: Dict[int, int] = {}
        self.last_price: Optional[float] = None
        self.prev_trade_price: Optional[float] = None
        self.tape: List[dict] = []       # rolling, newest appended last
        self.events: List[dict] = []
        self.frames: List[dict] = []
        self._next_frame = 0

    # --- mutation -------------------------------------------------------- #
    def _apply_level(self, side: Dict[int, int], price_raw: int, size: int) -> None:
        if size <= 0:
            side.pop(price_raw, None)
        else:
            side[price_raw] = size

    def apply(self, mtype: int, et_min: int, size: int, price_raw: int) -> None:
        # Snapshot every cadence boundary we've now passed *before* applying this
        # message, so frame M reflects the book as it stood entering minute M.
        while self._next_frame < len(FRAME_MINUTES) and et_min >= FRAME_MINUTES[self._next_frame]:
            self._snapshot(FRAME_MINUTES[self._next_frame])
            self._next_frame += 1

        if mtype == _BUY:
            self._apply_level(self.bids, price_raw, size)
        elif mtype == _SELL:
            self._apply_level(self.asks, price_raw, size)
        elif mtype == _TRADE:
            self._record_trade(et_min, size, price_raw)

    def _best(self):
        best_bid = max(self.bids) if self.bids else None
        best_ask = min(self.asks) if self.asks else None
        return best_bid, best_ask

    def _record_trade(self, et_min: int, size: int, price_raw: int) -> None:
        price = round(price_raw / _PRICE_DIV, 2)
        best_bid, best_ask = self._best()
        # Side is not carried on a DEEP trade report; infer it honestly with the
        # standard quote/tick test against the prevailing book.
        side = "buy"
        if best_ask is not None and price_raw >= best_ask:
            side = "buy"
        elif best_bid is not None and price_raw <= best_bid:
            side = "sell"
        elif self.prev_trade_price is not None:
            side = "buy" if price > self.prev_trade_price else "sell" if price < self.prev_trade_price else side
        self.prev_trade_price = price
        self.last_price = price

        is_block = size >= self.block_threshold
        is_sweep = (not is_block) and size >= self.sweep_threshold
        h, m = divmod(et_min, 60)
        rec = {
            "time": f"{h:02d}:{m:02d}",
            "price": price,
            "size": float(size),
            "side": side,
            "venue": "IEX",
            "isBlock": is_block,
            "isSweep": is_sweep,
        }
        self.tape.append(rec)
        if len(self.tape) > TAPE_BUFFER:
            del self.tape[:-TAPE_BUFFER]
        if is_block or is_sweep:
            span = max(SESSION_END - SESSION_START, 1)
            self.events.append({
                "time": rec["time"],
                "type": "block" if is_block else "sweep",
                "side": side,
                "price": price,
                "size": float(size),
                "pos": round((et_min - SESSION_START) / span, 4),
            })

    # --- snapshot -------------------------------------------------------- #
    def _ladder(self, side: Dict[int, int], descending: bool):
        prices = sorted(side, reverse=descending)[:LEVELS]
        rows = [{"price": round(p / _PRICE_DIV, 2), "size": float(side[p]), "depth": 0.0} for p in prices]
        mx = max((r["size"] for r in rows), default=1.0) or 1.0
        for r in rows:
            r["depth"] = round(r["size"] / mx, 3)
        return rows

    def _snapshot(self, fmin: int) -> None:
        if not self.bids and not self.asks:
            return  # no real book yet; don't emit an empty pre-open frame
        bids = self._ladder(self.bids, descending=True)
        asks = self._ladder(self.asks, descending=False)
        best_bid, best_ask = self._best()
        if best_bid is not None and best_ask is not None:
            spread = round((best_ask - best_bid) / _PRICE_DIV, 2)
            mid = (best_bid + best_ask) / 2 / _PRICE_DIV
        else:
            spread = 0.0
            one = best_bid if best_bid is not None else best_ask
            mid = one / _PRICE_DIV if one is not None else 0.0
        last_price = round(self.last_price if self.last_price is not None else mid, 2)
        tape = list(reversed(self.tape[-TAPE_LEN:]))
        h, m = divmod(fmin, 60)
        self.frames.append({
            "time": f"{h:02d}:{m:02d}",
            "lastPrice": last_price,
            "spread": spread,
            "bids": bids,
            "asks": asks,
            "tape": tape,
        })

    def finalize(self, et_min_seen: int) -> None:
        """Flush any cadence frames the clock reached but never crossed (e.g. the
        16:00 frame when the last trade of the day was a touch before the close)."""
        while self._next_frame < len(FRAME_MINUTES) and et_min_seen >= FRAME_MINUTES[self._next_frame]:
            self._snapshot(FRAME_MINUTES[self._next_frame])
            self._next_frame += 1

    def payload(self, session_iso: str) -> Optional[dict]:
        if len(self.frames) < MIN_FRAMES:
            return None
        last = self.frames[-1]
        return {
            "symbol": self.symbol,
            "name": self.name,
            "lastPrice": last["lastPrice"],
            "spread": last["spread"],
            "bids": last["bids"],
            "asks": last["asks"],
            "tape": last["tape"],
            "timestamp": last["time"],
            "selectedIndex": len(self.frames) - 1,
            "isLive": True,
            "frames": self.frames,
            "events": self.events,
            "blockThreshold": round(self.block_threshold, 0),
            "sessionStart": "09:30",
            "sessionEnd": "16:00",
            "session": session_iso,
            "venue": "IEX",
            "replayReal": True,
            "coverage": (
                f"Real IEX DEEP depth-of-book replay · venue-only (IEX prints, "
                f"not the consolidated tape) · T+1 session {session_iso}"
            ),
            "source": "IEX DEEP (venue-only, T+1)",
        }


class Reconstructor:
    """Drives a set of :class:`_SymbolBook`\\ s from decoded DEEP messages. Split
    out from the wire parser so it can be unit-tested with hand-built messages."""

    def __init__(
        self,
        symbols: Set[str],
        session_iso: str,
        names: Optional[Dict[str, str]] = None,
        block_thresholds: Optional[Dict[str, float]] = None,
    ) -> None:
        names = names or {}
        block_thresholds = block_thresholds or {}
        self.session_iso = session_iso
        self.offset = _et_offset_seconds(session_iso)
        self.books: Dict[str, _SymbolBook] = {
            s.upper(): _SymbolBook(s.upper(), names.get(s.upper(), s.upper()),
                                   block_thresholds.get(s.upper(), 2000.0))
            for s in symbols
        }
        self.max_et_min = -1

    def et_minute(self, ts_ns: int) -> int:
        et_sec = ts_ns // 1_000_000_000 + self.offset
        return int((et_sec % 86400) // 60)

    def apply(self, mtype: int, ts_ns: int, symbol: str, size: int, price_raw: int) -> None:
        book = self.books.get(symbol.upper())
        if book is None:
            return
        et_min = self.et_minute(ts_ns)
        if et_min > self.max_et_min:
            self.max_et_min = et_min
        book.apply(mtype, et_min, size, price_raw)

    def past_session(self) -> bool:
        return self.max_et_min > SESSION_END

    def finalize(self) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        end = self.max_et_min if self.max_et_min >= 0 else SESSION_END
        for sym, book in self.books.items():
            book.finalize(end)
            p = book.payload(self.session_iso)
            if p is not None:
                out[sym] = p
        return out


def reconstruct(
    symbols: Set[str],
    link: str,
    session_iso: str,
    names: Optional[Dict[str, str]] = None,
    block_thresholds: Optional[Dict[str, float]] = None,
    chunk_size: int = 1 << 20,
) -> Dict[str, dict]:
    """Stream the session's DEEP capture and rebuild a real order-book replay for
    each requested symbol. Returns ``{symbol: panel_payload}``; symbols with no
    real IEX depth that day are simply absent. Blocking and slow (a full session
    is ~13 GB gzipped) — intended to run in a background worker thread, never in
    the request path."""
    if not symbols:
        return {}
    recon = Reconstructor(symbols, session_iso, names, block_thresholds)
    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)  # gzip
    t0 = time.time()
    comp = 0

    def _decompressed_chunks() -> Iterator[bytes]:
        nonlocal comp
        timeout = httpx.Timeout(connect=20.0, read=120.0, write=120.0, pool=120.0)
        with _resilient.stream("iex_deep", link, timeout=timeout, follow_redirects=True) as resp:
            for raw in resp.iter_bytes(chunk_size):
                comp += len(raw)
                out = dec.decompress(raw)
                if out:
                    yield out

    for mtype, ts_ns, sym, size, price_raw in iter_deep_messages(_decompressed_chunks(), symbols):
        recon.apply(mtype, ts_ns, sym, size, price_raw)
        # Once the clock is past the close we have every RTH frame; stop pulling
        # the (still large) after-hours tail of the capture.
        if recon.past_session():
            break

    result = recon.finalize()
    log.info(
        "IEX DEEP reconstruct %s session=%s -> %d/%d symbols in %.0fs (%.1f GB read)",
        sorted(symbols), session_iso, len(result), len(symbols),
        time.time() - t0, comp / 1e9,
    )
    return result
