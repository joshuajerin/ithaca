"""Standalone tests for the real IEX DEEP order-book reconstruction.

Runnable two ways:
    python artifacts/api-server/tests/test_orderbook_replay.py   # standalone
    pytest artifacts/api-server/tests/test_orderbook_replay.py    # if installed

No network: we hand-build a tiny pcapng capture carrying a handful of DEEP
messages to exercise the wire decoder (`iter_deep_messages`, including chunk
boundaries), then drive `Reconstructor` directly to verify the panel payload
schema, frame cadence, depth-ladder ordering, spread, honest side inference, and
block-event detection.
"""
from __future__ import annotations

import os
import struct
import sys

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app.sources import iex_deep  # noqa: E402

SESSION = "2026-06-08"


# --------------------------------------------------------------------------- #
# Wire-format fixture builders (mirror the layout documented in iex_deep.py)
# --------------------------------------------------------------------------- #
def _deep_body(mtype: int, ts_ns: int, symbol: str, size: int, price_raw: int) -> bytes:
    """One 30-byte DEEP message body."""
    body = bytearray(30)
    body[0] = mtype
    body[1] = 0  # flags (unused by the decoder)
    struct.pack_into("<q", body, 2, ts_ns)
    body[10:18] = symbol.upper().encode("ascii").ljust(8)[:8]
    struct.pack_into("<I", body, 18, size)
    struct.pack_into("<q", body, 22, price_raw)
    return bytes(body)


def _iextp_segment(bodies: list[bytes]) -> bytes:
    """Wrap message bodies in an IEX-TP segment (40-byte header + framed msgs)."""
    msgs = bytearray()
    for b in bodies:
        msgs += struct.pack("<H", len(b)) + b
    seg = bytearray(40)
    seg[0] = 0x01  # version
    struct.pack_into("<H", seg, 2, iex_deep._DEEP_PROTO)
    struct.pack_into("<H", seg, 16, len(msgs))  # payload length
    struct.pack_into("<H", seg, 18, len(bodies))  # message count
    return bytes(seg) + bytes(msgs)


def _udp_packet(seg: bytes) -> bytes:
    """Ethernet II + IPv4(20) + UDP(8) framing around an IEX-TP segment."""
    pkt = bytearray(42)
    pkt[12] = 0x08  # ethertype 0x0800 (IPv4)
    pkt[13] = 0x00
    pkt[14] = 0x45  # IPv4 version 4, IHL 5 (20 bytes)
    pkt[14 + 9] = 17  # protocol = UDP
    # UDP header occupies pkt[34:42]; contents are irrelevant to the decoder.
    return bytes(pkt) + seg


def _shb() -> bytes:
    """Minimal pcapng Section Header Block (little-endian)."""
    blk = bytearray(28)
    struct.pack_into("<I", blk, 0, 0x0A0D0D0A)  # block type
    struct.pack_into("<I", blk, 4, 28)          # total length
    struct.pack_into("<I", blk, 8, 0x1A2B3C4D)  # byte-order magic
    struct.pack_into("<H", blk, 12, 1)          # major
    struct.pack_into("<H", blk, 14, 0)          # minor
    struct.pack_into("<q", blk, 16, -1)         # section length (unspecified)
    struct.pack_into("<I", blk, 24, 28)         # trailing total length
    return bytes(blk)


def _epb(pkt: bytes) -> bytes:
    """Wrap a packet in an Enhanced Packet Block."""
    caplen = len(pkt)
    pad = (-caplen) % 4
    total = 28 + caplen + pad + 4
    blk = bytearray(total)
    struct.pack_into("<I", blk, 0, 0x00000006)  # block type
    struct.pack_into("<I", blk, 4, total)
    struct.pack_into("<I", blk, 8, 0)           # interface id
    struct.pack_into("<I", blk, 12, 0)          # ts high
    struct.pack_into("<I", blk, 16, 0)          # ts low
    struct.pack_into("<I", blk, 20, caplen)     # captured length
    struct.pack_into("<I", blk, 24, caplen)     # original length
    blk[28:28 + caplen] = pkt
    struct.pack_into("<I", blk, total - 4, total)  # trailing total length
    return bytes(blk)


def _chunks(data: bytes, n: int):
    """Yield `data` in fixed-size pieces to exercise cross-chunk buffering."""
    for i in range(0, len(data), n):
        yield data[i:i + n]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_wire_decoder_roundtrip() -> None:
    msgs = [
        (iex_deep._BUY, 1_000, "TEST", 300, 1_000_000),
        (iex_deep._SELL, 2_000, "TEST", 250, 1_000_500),
        (iex_deep._TRADE, 3_000, "TEST", 800, 1_000_200),
        (iex_deep._BUY, 4_000, "OTHR", 100, 990_000),  # filtered out below
    ]
    seg = _iextp_segment([_deep_body(*m) for m in msgs])
    cap = _shb() + _epb(_udp_packet(seg))

    # Feed in deliberately tiny chunks so the block buffer must span boundaries.
    decoded = list(iex_deep.iter_deep_messages(_chunks(cap, 7), symbols={"TEST"}))

    assert len(decoded) == 3, f"expected 3 TEST messages, got {len(decoded)}"
    types = [d[0] for d in decoded]
    assert types == [iex_deep._BUY, iex_deep._SELL, iex_deep._TRADE]
    # (mtype, ts_ns, symbol, size, price_raw)
    assert decoded[0][2] == "TEST"
    assert decoded[0][3] == 300 and decoded[0][4] == 1_000_000
    assert decoded[2][3] == 800 and decoded[2][4] == 1_000_200
    # Symbol filter must drop the OTHR message entirely.
    assert all(d[2] == "TEST" for d in decoded)
    print("ok test_wire_decoder_roundtrip")


def test_wire_decoder_unfiltered_sees_all() -> None:
    msgs = [
        (iex_deep._BUY, 1_000, "AAA", 100, 500_000),
        (iex_deep._SELL, 2_000, "BBB", 200, 600_000),
    ]
    seg = _iextp_segment([_deep_body(*m) for m in msgs])
    cap = _shb() + _epb(_udp_packet(seg))
    decoded = list(iex_deep.iter_deep_messages(_chunks(cap, 5)))
    syms = sorted(d[2] for d in decoded)
    assert syms == ["AAA", "BBB"], syms
    print("ok test_wire_decoder_unfiltered_sees_all")


def _ts_for(et_min: int) -> int:
    """Nanosecond timestamp that maps to the given ET minute-of-day for SESSION."""
    offset = iex_deep._et_offset_seconds(SESSION)
    return (et_min * 60 - offset) * 1_000_000_000


def test_reconstructor_builds_real_payload() -> None:
    recon = iex_deep.Reconstructor(
        {"TEST"}, SESSION, names={"TEST": "Test Corp"},
        block_thresholds={"TEST": 500.0},
    )

    # Populate a depth ladder just before the open: three bids, two asks.
    for pr, sz in [(1_000_000, 400), (999_900, 600), (999_800, 300)]:
        recon.apply(iex_deep._BUY, _ts_for(569), "TEST", sz, pr)
    for pr, sz in [(1_000_500, 500), (1_000_600, 200)]:
        recon.apply(iex_deep._SELL, _ts_for(569), "TEST", sz, pr)

    # A trade at the offer (price >= best ask) must be inferred as a BUY, and a
    # 1,000-share print clears the 500 block threshold -> a block event.
    recon.apply(iex_deep._TRADE, _ts_for(575), "TEST", 1_000, 1_000_500)

    # A trade at the bid (price <= best bid) must be inferred as a SELL.
    recon.apply(iex_deep._TRADE, _ts_for(585), "TEST", 100, 1_000_000)

    # Push the clock just past the close so every cadence frame is flushed.
    recon.apply(iex_deep._TRADE, _ts_for(961), "TEST", 100, 1_000_100)

    out = recon.finalize()
    assert "TEST" in out, "reconstruction produced no payload for TEST"
    p = out["TEST"]

    # Provenance / honesty contract.
    assert p["replayReal"] is True
    assert p["venue"] == "IEX"
    assert p["session"] == SESSION
    assert "venue-only" in p["coverage"].lower()
    assert p["source"] == "IEX DEEP (venue-only, T+1)"
    assert p["name"] == "Test Corp"

    # Frame schema + cadence: one frame every 10 min across 09:30..16:00.
    frames = p["frames"]
    assert len(frames) >= iex_deep.MIN_FRAMES
    assert frames[0]["time"] == "09:30"
    assert frames[-1]["time"] == "16:00"
    for fr in frames:
        for key in ("time", "lastPrice", "spread", "bids", "asks", "tape"):
            assert key in fr, f"frame missing {key}"
        # Depth ladder is capped and price-sorted (bids desc, asks asc).
        assert len(fr["bids"]) <= iex_deep.LEVELS
        assert len(fr["asks"]) <= iex_deep.LEVELS
        bid_prices = [b["price"] for b in fr["bids"]]
        ask_prices = [a["price"] for a in fr["asks"]]
        assert bid_prices == sorted(bid_prices, reverse=True)
        assert ask_prices == sorted(ask_prices)
        # Every depth bar is normalised into [0, 1].
        for lvl in fr["bids"] + fr["asks"]:
            assert 0.0 <= lvl["depth"] <= 1.0

    # Best bid (100.00) below best ask (100.05) -> positive spread.
    assert frames[-1]["spread"] > 0

    # Honest side inference recorded on the tape.
    sides = {t["side"] for fr in frames for t in fr["tape"]}
    assert "buy" in sides and "sell" in sides, sides

    # The 1,000-share print is flagged as a block event.
    blocks = [e for e in p["events"] if e["type"] == "block"]
    assert blocks, "expected a block event for the 1,000-share trade"
    assert blocks[0]["side"] == "buy"
    assert blocks[0]["size"] == 1_000.0
    assert 0.0 <= blocks[0]["pos"] <= 1.0
    print("ok test_reconstructor_builds_real_payload")


def test_thin_symbol_yields_no_payload() -> None:
    """A name IEX barely traded (one lonely level, no real book) must not be
    promoted to a 'real' replay — payload() returns None below MIN_FRAMES."""
    recon = iex_deep.Reconstructor({"THIN"}, SESSION)
    recon.apply(iex_deep._BUY, _ts_for(600), "THIN", 100, 500_000)
    out = recon.finalize()
    assert "THIN" not in out, "thin symbol should not yield a real payload"
    print("ok test_thin_symbol_yields_no_payload")


def _run_all() -> None:
    test_wire_decoder_roundtrip()
    test_wire_decoder_unfiltered_sees_all()
    test_reconstructor_builds_real_payload()
    test_thin_symbol_yields_no_payload()
    print("\nALL ORDER-BOOK REPLAY TESTS PASSED")


if __name__ == "__main__":
    _run_all()
