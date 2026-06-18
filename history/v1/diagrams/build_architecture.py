#!/usr/bin/env python3
"""Generate the doomberg Agentic Terminal architecture diagram as an SVG.

Hand-laid dark-editorial diagram with the Agent Harness as the central core and
the numbered request-flow path (1..7) overlaid. Pure stdlib; emits an SVG that is
rasterized to a high-resolution PNG by ImageMagick (see render step).
"""
from __future__ import annotations

import html

W, H = 1760, 1330

# ----- palette (terminal dark editorial) -----
BG      = "#0a0b0d"
PANEL   = "#101216"
CARD    = "#16181d"
CARD2   = "#1b1e24"
LINE    = "#27272a"
LINE2   = "#3a3a42"
INK     = "#f5f5f6"
MUT     = "#a1a1aa"
DIM     = "#71717a"
FAINT   = "#52525b"

ACCENT     = "#e3b25c"   # amber — the core + numbered flow
ACCENT_DK  = "#5f4d28"
BLUE   = "#74a9cf"       # frontend
TEAL   = "#5bb6a8"       # transport/api
VIOLET = "#a99bf2"       # ai clients
GREEN  = "#6fb87f"       # data
ROSE   = "#d3899c"       # shared contract

SERIF = "Georgia, 'DejaVu Serif', serif"
SANS  = "Helvetica, 'DejaVu Sans', Arial, sans-serif"
MONO  = "'DejaVu Sans Mono', Menlo, monospace"

out: list[str] = []
def add(s: str) -> None:
    out.append(s)

def esc(s: str) -> str:
    return html.escape(s, quote=True)

def rect(x, y, w, h, rx=10, fill=PANEL, stroke=LINE, sw=1.0, dash=None, opacity=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    o = f' opacity="{opacity}"' if opacity is not None else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}{o}/>')

def line(x1, y1, x2, y2, stroke=LINE, sw=1.0, dash=None, opacity=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    o = f' opacity="{opacity}"' if opacity is not None else ""
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}{o}/>')

def text(x, y, s, size=14, fill=INK, family=SANS, weight="normal",
         anchor="start", spacing=None, italic=False, opacity=None):
    sp = f' letter-spacing="{spacing}"' if spacing is not None else ""
    st = ' font-style="italic"' if italic else ""
    o = f' opacity="{opacity}"' if opacity is not None else ""
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"{sp}{st}{o}>{esc(s)}</text>')

def lines(x, y, rows, size=12.5, fill=MUT, family=SANS, lh=16, anchor="start"):
    for i, r in enumerate(rows):
        text(x, y + i * lh, r, size=size, fill=fill, family=family, anchor=anchor)

def zone(x, y, w, h, label, sublabel, accent, fill=PANEL):
    rect(x, y, w, h, rx=14, fill=fill, stroke=LINE, sw=1.4)
    # accent tab on the left edge
    add(f'<rect x="{x}" y="{y+16}" width="4" height="34" rx="2" fill="{accent}"/>')
    text(x + 22, y + 30, label, size=12, fill=accent, family=SANS, weight="bold",
         spacing="2.4")
    text(x + 22, y + 48, sublabel, size=12.5, fill=DIM, family=MONO)

def card(x, y, w, h, title, rows, accent=None, fill=CARD, title_size=14.5,
         mono_title=False, rowfill=MUT, rowsize=11.8, lh=15):
    rect(x, y, w, h, rx=10, fill=fill, stroke=LINE, sw=1.1)
    if accent:
        add(f'<rect x="{x}" y="{y}" width="{w}" height="3" rx="1.5" fill="{accent}"/>')
    tf = MONO if mono_title else SANS
    text(x + 14, y + 27, title, size=title_size, fill=INK, family=tf, weight="bold")
    if rows:
        lines(x + 14, y + 46, rows, size=rowsize, fill=rowfill, lh=lh)

def chip(x, y, w, label, fill=CARD2, stroke=LINE, txt=MUT, h=26):
    rect(x, y, w, h, rx=13, fill=fill, stroke=stroke, sw=1.0)
    text(x + w / 2, y + 17, label, size=11.5, fill=txt, family=MONO, anchor="middle")

def badge(cx, cy, n):
    add(f'<circle cx="{cx}" cy="{cy}" r="12.5" fill="{BG}" stroke="{ACCENT}" stroke-width="1.6"/>')
    text(cx, cy + 4.5, str(n), size=13, fill=ACCENT, family=SANS, weight="bold", anchor="middle")

def flow(points, color=ACCENT, sw=2.2, marker="af", dash=None):
    d = "M " + " L ".join(f"{x} {y}" for x, y in points)
    da = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" '
        f'marker-end="url(#{marker})" stroke-linejoin="round" stroke-linecap="round"{da}/>')

# ----------------------------------------------------------------- defs
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" font-family="{SANS}">')
add('<defs>')
add(f'<radialGradient id="bgg" cx="50%" cy="34%" r="80%">'
    f'<stop offset="0%" stop-color="#101319"/>'
    f'<stop offset="60%" stop-color="{BG}"/>'
    f'<stop offset="100%" stop-color="#060709"/></radialGradient>')
for mid, col in (("af", ACCENT), ("gf", LINE2), ("vf", VIOLET), ("gn", GREEN)):
    add(f'<marker id="{mid}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7.5" '
        f'markerHeight="7.5" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{col}"/></marker>')
add(f'<linearGradient id="coreg" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0%" stop-color="#1c1a14"/>'
    f'<stop offset="100%" stop-color="#121117"/></linearGradient>')
add('</defs>')
add(f'<rect width="{W}" height="{H}" fill="url(#bgg)"/>')

# ----------------------------------------------------------------- header
text(40, 64, "doomberg", size=46, fill=INK, family=SERIF, weight="bold")
text(330, 64, "Agentic Terminal", size=23, fill=ACCENT, family=SERIF, italic=True)
text(42, 96, "TECHNICAL ARCHITECTURE", size=12.5, fill=MUT, spacing="3.6", weight="bold")
text(42, 118, "A self-building market-intelligence dashboard \u2014 the Agent Harness sits at the core, "
              "turning one natural-language query into a live panel dashboard.",
     size=13.5, fill=DIM, family=SANS)
# legend (top right)
lx = 1330
rect(lx, 36, 390, 84, rx=10, fill=PANEL, stroke=LINE, sw=1.1)
text(lx + 16, 60, "REQUEST FLOW", size=11, fill=ACCENT, weight="bold", spacing="2.6")
badge(lx + 26, 90, 1); text(lx + 44, 95, "query \u2192 orchestrate \u2192 harness", size=12, fill=MUT)
text(lx + 250, 95, "\u2192 panels \u2192 render", size=12, fill=MUT)
text(lx + 16, 112, "amber path = one round-trip   \u00b7   \u2466 = self-building side loop",
     size=10.8, fill=DIM)

# ----- spine geometry -----
SX, SW = 372, 1016         # central spine
IN_X, IN_W = SX + 20, SW - 40

# zone y-bands
FE_Y, FE_H = 206, 196
AP_Y, AP_H = 432, 140
CO_Y, CO_H = 600, 360
DA_Y, DA_H = 990, 230

# ================================================================ USER
upill_x, upill_w = 790, 180
rect(upill_x, 150, upill_w, 44, rx=22, fill=CARD2, stroke=LINE2, sw=1.2)
text(880, 170, "USER", size=11, fill=INK, weight="bold", spacing="3", anchor="middle")
text(880, 186, "types a query / speaks", size=11, fill=DIM, anchor="middle", family=MONO)

# ================================================================ FRONTEND
zone(SX, FE_Y, SW, FE_H, "FRONTEND \u00b7 AGENTIC TERMINAL", "React + Vite \u00b7 artifacts/terminal", BLUE)
fcw = 233
fx = [390, 639, 888, 1137]
fy, fh = 272, 116
card(fx[0], fy, fcw, fh, "Console", ["ChatPanel.tsx", "typed chat \u00b7 streamed", "answers (SSE)"],
     accent=BLUE, mono_title=False)
card(fx[1], fy, fcw, fh, "Voice Orb", ["VoicePanel.tsx", "push-to-talk \u00b7 STT in,", "TTS narration out"],
     accent=BLUE)
card(fx[2], fy, fcw, fh, "Dashboard", ["Dashboard.tsx", "12-column panel grid,", "drag / resize / fade"],
     accent=BLUE)
card(fx[3], fy, fcw, fh, "Dynamic Panel", ["DynamicPanel.tsx", "runtime-loads AI panels", "(sucrase in browser)"],
     accent=BLUE)

# ================================================================ TRANSPORT / API
zone(SX, AP_Y, SW, AP_H, "TRANSPORT / API \u00b7 FASTAPI", "artifacts/api-server \u00b7 app/main.py", TEAL)
ep = [
    ("/api/orchestrate", 150), ("/api/orchestrate/stream  SSE", 220),
    ("/api/transcribe  STT", 170), ("TTS / speak", 110),
    ("/api/feature-request  SSE", 210), ("/api/generated-panels", 180),
    ("/api/features", 120),
]
cx = 392
cy = 492
gap = 12
for label, w in ep:
    if cx + w > 1368:
        cx = 392
        cy += 36
    chip(cx, cy, w, label, txt=MUT)
    cx += w + gap

# ================================================================ CORE — AGENT HARNESS
rect(SX, CO_Y, SW, CO_H, rx=16, fill="url(#coreg)", stroke=ACCENT, sw=2.0)
add(f'<rect x="{SX}" y="{CO_Y+18}" width="4" height="40" rx="2" fill="{ACCENT}"/>')
text(SX + 22, CO_Y + 34, "CORE \u00b7 AGENT HARNESS", size=14, fill=ACCENT, weight="bold", spacing="3")
text(SX + 22, CO_Y + 54, "orchestration engine \u2014 decides what to build, builds it, validates it",
     size=12.5, fill=MUT, family=SANS)
text(1368, CO_Y + 34, "the core", size=12, fill=ACCENT_DK, anchor="end", family=SERIF, italic=True)

ccw = 313
cxs = [392, 723, 1054]
ccy, cch = 672, 132
card(cxs[0], ccy, ccw, cch, "Orchestrator",
     ["agent.py", "LLM tool-calling picks which",
      "skills / panels to build;",
      "context-aware keep / drop of",
      "panels; question-vs-build split"],
     accent=ACCENT, fill=CARD2, rowsize=11.6, lh=14.6)
card(cxs[1], ccy, ccw, cch, "Harness",
     ["harness.py", "runs each skill builder \u2192",
      "validates vs Pydantic model \u2192",
      "Panel Envelope {id, layout,",
      "status, data}; pack_layout grid"],
     accent=ACCENT, fill=CARD2, rowsize=11.6, lh=14.6)
card(cxs[2], ccy, ccw, cch, "Skill Registry",
     ["skills.py", "each skill = metadata",
      "(params / JSON schema +",
      "description) + a builder fn;",
      "~50 built-in panel types"],
     accent=ACCENT, fill=CARD2, rowsize=11.6, lh=14.6)

# self-building pipeline strip (full width)
ppx, ppy, ppw, pph = 392, 822, 976, 116
rect(ppx, ppy, ppw, pph, rx=10, fill=CARD, stroke=ACCENT_DK, sw=1.3, dash="5 4")
add(f'<rect x="{ppx}" y="{ppy}" width="{ppw}" height="3" rx="1.5" fill="{ACCENT}"/>')
badge(ppx + 24, ppy + 20, 7)
text(ppx + 48, ppy + 26, "Self-Building Feature Pipeline", size=14, fill=INK, weight="bold")
text(ppx + 320, ppy + 26, "AI writes a new skill + panel at runtime \u2014 hot-loaded in-process, no restart",
     size=11.6, fill=DIM)
# three mini nodes
mn_y, mn_h = ppy + 44, 50
mnodes = [
    ("feature_builder.py", "LLM authors Python", ppx + 14, 250),
    ("code_guard.py", "AST allow-list audit", ppx + 300, 230),
    ("dynamic_skills.py", "validate \u00b7 hot-load", ppx + 560, 230),
]
mids = []
for title, sub, mx, mw in mnodes:
    rect(mx, mn_y, mw, mn_h, rx=8, fill=CARD2, stroke=LINE, sw=1.0)
    text(mx + 12, mn_y + 22, title, size=12.5, fill=INK, family=MONO)
    text(mx + 12, mn_y + 39, sub, size=11, fill=DIM)
    mids.append((mx, mw))
# arrows between mini nodes
ay = mn_y + mn_h / 2
flow([(mids[0][0] + mids[0][1], ay), (mids[1][0] - 4, ay)], color=ACCENT, sw=1.8, marker="af")
flow([(mids[1][0] + mids[1][1], ay), (mids[2][0] - 4, ay)], color=ACCENT, sw=1.8, marker="af")
# register result -> back to Skill Registry (loop up)
reg_x = mids[2][0] + mids[2][1]
text(reg_x + 16, mn_y + 22, "registered into", size=11, fill=DIM)
text(reg_x + 16, mn_y + 39, "Skill Registry \u2191", size=11.5, fill=ACCENT, family=MONO)

# ================================================================ AI CLIENTS (left rail)
ai_x, ai_w, ai_y, ai_h = 40, 300, 648, 264
zone(ai_x, ai_y, ai_w, ai_h, "AI CLIENTS \u00b7 ai.py", "via Replit AI proxy", VIOLET)
aiy = 706
aih = 55
ais = [
    ("GPT \u00b7 orchestration", "tool-calling + analysis + streamed answers"),
    ("gpt-audio \u00b7 TTS", "spoken narration for Voice Mode"),
    ("transcribe \u00b7 STT", "mic audio \u2192 text for non-Web-Speech browsers"),
]
for i, (t, s) in enumerate(ais):
    yy = aiy + i * (aih + 12)
    rect(ai_x + 18, yy, ai_w - 36, aih, rx=9, fill=CARD, stroke=LINE, sw=1.0)
    add(f'<rect x="{ai_x+18}" y="{yy}" width="3" height="{aih}" rx="1.5" fill="{VIOLET}"/>')
    text(ai_x + 32, yy + 22, t, size=13, fill=INK, weight="bold", family=MONO)
    text(ai_x + 32, yy + 40, s, size=10.6, fill=DIM)

# ================================================================ DATA LAYER
zone(SX, DA_Y, SW, DA_H, "DATA LAYER", "live data, mediated \u2014 never an empty panel", GREEN)
# repository bar
rpx, rpy, rpw, rph = 392, DA_Y + 56, 976, 34
rect(rpx, rpy, rpw, rph, rx=8, fill=CARD2, stroke=LINE, sw=1.0)
add(f'<rect x="{rpx}" y="{rpy}" width="3" height="{rph}" rx="1.5" fill="{GREEN}"/>')
text(rpx + 14, rpy + 22, "Repository  \u00b7  repo.py", size=13, fill=INK, weight="bold", family=MONO)
text(rpx + 320, rpy + 22, "mediates live data vs. mocks; surfaces asOf / source freshness",
     size=11.4, fill=DIM)
# three sources
dcw = 314
dxs = [392, 722, 1052]
dcy, dch = rpy + rph + 16, 104
card(dxs[0], dcy, dcw, dch, "Live Sources",
     ["sources/  \u00b7  resilient",
      "Yahoo prices / news / fundamentals;",
      "US Treasury + FRED (rates, credit);",
      "retry + circuit breaker per source"],
     accent=GREEN, rowsize=11.4, lh=15)
card(dxs[1], dcy, dcw, dch, "Postgres",
     ["db.py  \u00b7  lib/db (Drizzle)",
      "fundamentals, news,",
      "OHLCV price history;",
      "ingested by a background worker"],
     accent=GREEN, rowsize=11.4, lh=15)
card(dxs[2], dcy, dcw, dch, "Mock / Curated",
     ["data.py",
      "deterministic fallback that",
      "keeps the terminal warm when",
      "a source is throttled or down"],
     accent=GREEN, rowsize=11.4, lh=15)

# ================================================================ SHARED CONTRACT (right rail)
sc_x, sc_w, sc_y, sc_h = 1420, 300, 206, 1014
zone(sc_x, sc_y, sc_w, sc_h, "SHARED CONTRACT", "the typed FE \u2194 BE boundary", ROSE)
# api-spec box
b1y = sc_y + 70
rect(sc_x + 24, b1y, sc_w - 48, 116, rx=10, fill=CARD, stroke=LINE, sw=1.1)
add(f'<rect x="{sc_x+24}" y="{b1y}" width="{sc_w-48}" height="3" rx="1.5" fill="{ROSE}"/>')
text(sc_x + 40, b1y + 28, "lib/api-spec", size=14, fill=INK, weight="bold", family=MONO)
lines(sc_x + 40, b1y + 50, ["OpenAPI schema \u2014 the",
                            "single source of truth",
                            "for every endpoint",
                            "and panel data shape"], size=11.4, fill=MUT, lh=16)
# arrow down (codegen)
mid_x = sc_x + sc_w / 2
flow([(mid_x, b1y + 116 + 6), (mid_x, b1y + 116 + 52)], color=ROSE, sw=2.0, marker="vf")
text(mid_x + 12, b1y + 116 + 36, "codegen", size=11, fill=DIM, family=MONO)
# api-client box
b2y = b1y + 116 + 58
rect(sc_x + 24, b2y, sc_w - 48, 116, rx=10, fill=CARD, stroke=LINE, sw=1.1)
add(f'<rect x="{sc_x+24}" y="{b2y}" width="{sc_w-48}" height="3" rx="1.5" fill="{ROSE}"/>')
text(sc_x + 40, b2y + 28, "lib/api-client-react", size=13.5, fill=INK, weight="bold", family=MONO)
lines(sc_x + 40, b2y + 50, ["generated React hooks",
                            "+ types consumed by",
                            "the frontend \u2014 one",
                            "compile-checked contract"], size=11.4, fill=MUT, lh=16)
# vertical tie note down the rail
text(mid_x, b2y + 190, "every request &", size=11.5, fill=DIM, anchor="middle")
text(mid_x, b2y + 208, "panel envelope is", size=11.5, fill=DIM, anchor="middle")
text(mid_x, b2y + 226, "typed end-to-end", size=11.5, fill=ROSE, anchor="middle", weight="bold")
# faint dashed ties: api-client-react <-> frontend, api-spec <-> transport
line(SX + SW + 2, FE_Y + 96, sc_x - 2, FE_Y + 96, ROSE, sw=1.1, dash="3 5", opacity=0.5)
line(SX + SW + 2, AP_Y + 60, sc_x - 2, AP_Y + 60, ROSE, sw=1.1, dash="3 5", opacity=0.5)

# ================================================================ FLOW ARROWS (1..7)
DN = 700    # downward request path (left of spine center)
UP = 1060   # upward response path (right of spine center)

# (1) USER -> Console/Voice
flow([(880, 194 + 2), (880, FE_Y - 4)], color=ACCENT, sw=2.4)
badge(916, FE_Y - 22, 1)

# (2) Console/Voice -> /api/orchestrate
flow([(DN, FE_Y + FE_H + 2), (DN, AP_Y - 4)], color=ACCENT, sw=2.4)
badge(DN - 24, (FE_Y + FE_H + AP_Y) / 2, 2)
text(DN + 14, (FE_Y + FE_H + AP_Y) / 2 + 4, "POST query (SSE)", size=10.8, fill=DIM, family=MONO)

# API -> Core (dispatch, unnumbered)
flow([(DN, AP_Y + AP_H + 2), (DN, CO_Y - 4)], color=ACCENT, sw=2.4)
text(DN + 14, (AP_Y + AP_H + CO_Y) / 2 + 4, "dispatch", size=10.8, fill=DIM, family=MONO)

# (3) Orchestrator -> AI clients (tool-calling)
oc_lx = cxs[0]                 # orchestrator card left x = 392
flow([(oc_lx - 2, ccy + 40), (ai_x + ai_w + 4, ccy + 40)], color=VIOLET, sw=2.2, marker="vf")
flow([(ai_x + ai_w + 4, ccy + 74), (oc_lx - 2, ccy + 74)], color=VIOLET, sw=1.6, marker="vf", dash="5 4")
badge(oc_lx - 30, ccy + 22, 3)
text((ai_x + ai_w + oc_lx) / 2, ccy + 30, "tool-calling", size=10.4, fill=DIM,
     family=MONO, anchor="middle")

# (4) Harness -> Repository -> sources (Core down to Data)
flow([(DN, CO_Y + CO_H + 2), (DN, DA_Y - 4)], color=ACCENT, sw=2.4)
badge(DN - 24, (CO_Y + CO_H + DA_Y) / 2, 4)
text(DN + 14, (CO_Y + CO_H + DA_Y) / 2 + 4, "build panels \u00b7 repo \u2192 sources", size=10.8, fill=DIM, family=MONO)

# (5) Core -> API (Panel Envelopes + grid -> DashboardSpec) [upward]
flow([(UP, CO_Y - 4), (UP, AP_Y + AP_H + 2)], color=ACCENT, sw=2.4)
badge(UP + 26, (CO_Y + AP_Y + AP_H) / 2, 5)
text(UP - 14, (CO_Y + AP_Y + AP_H) / 2 + 4, "Panel Envelopes \u2192 DashboardSpec",
     size=10.8, fill=DIM, family=MONO, anchor="end")

# (6) API -> Frontend (DashboardSpec -> render) [upward]
flow([(UP, AP_Y - 4), (UP, FE_Y + FE_H + 2)], color=ACCENT, sw=2.4)
badge(UP + 26, (AP_Y + FE_Y + FE_H) / 2, 6)
text(UP - 14, (AP_Y + FE_Y + FE_H) / 2 + 4, "render panels", size=10.8, fill=DIM, family=MONO, anchor="end")

# (7) self-building side loop: pipeline registers a new skill back into the registry
sk_cx = cxs[2] + ccw / 2       # skill registry card center x
flow([(sk_cx, ppy - 2), (sk_cx, ccy + cch + 3)], color=ACCENT, sw=2.0, marker="af", dash="6 4")

# ================================================================ footer
fy2 = 1252
line(40, fy2 - 14, W - 40, fy2 - 14, LINE, 1.0)
text(40, fy2 + 6, "Every box maps to real source under artifacts/api-server/app and artifacts/terminal/src.",
     size=11.5, fill=DIM)
text(40, fy2 + 26, "Built-in panels are validated against Pydantic models; AI-generated panels pass through untyped and render via DynamicPanel.",
     size=11.5, fill=FAINT)
text(W - 40, fy2 + 6, "doomberg \u00b7 Agentic Terminal", size=11.5, fill=DIM, anchor="end", family=SERIF, italic=True)

add('</svg>')

with open("diagrams/doomberg-architecture.svg", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("wrote diagrams/doomberg-architecture.svg")
