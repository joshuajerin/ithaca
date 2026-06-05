"""FastAPI application for the agentic terminal. Served under the /api prefix."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import agent, dynamic_skills, feature_builder, harness, models, repo, skills, state, worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Register any AI-generated skills authored in previous sessions before serving.
    dynamic_skills.load_generated_skills()
    await worker.start()
    try:
        yield
    finally:
        await worker.stop()


app = FastAPI(title="Agentic Terminal API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


@api.get("/healthz")
def healthz():
    from . import ai
    return {"status": "ok", "aiAvailable": ai.ai_available()}


@api.get("/skills", response_model=models.SkillCatalog)
def get_skills():
    return skills.skill_catalog()


@api.get("/sectors", response_model=models.SectorList)
def get_sectors():
    return {"sectors": repo.list_sectors()}


@api.get("/suggestions", response_model=models.SuggestionList)
def get_suggestions():
    return {"prompts": [
        "Give me a market overview of what's moving today",
        "Deep dive on NVIDIA",
        "Compare NVDA, AMD and TSM",
        "Screen the robotics & automation sector",
        "Show me the EV and automotive heatmap",
        "What's the latest news in cybersecurity?",
        "Screen biotech & pharma names",
        "Compare V, MA and PYPL in fintech",
        "Screen the cloud & software sector",
        "What's moving in clean & renewable energy?",
        "Show the defense & aerospace sector",
        "Screen the big banks & financials",
        "Heatmap of healthcare stocks",
        "Latest news in communications & media",
        "Screen industrials",
        "What's the sentiment on Palantir?",
        "DCF model for MSFT",
    ]}


def _build_default_dashboard() -> dict:
    cursor = {"x": 0, "y": 0, "rowH": 0}
    panels = []

    def add(panel_type, params, w, h):
        layout = harness.pack_layout(w, h, cursor)
        panels.append(harness.run_skill(panel_type, params, layout))

    add("heatmap", {}, 12, 3)
    add("price_chart", {"symbol": "NVDA", "range": "3M"}, 8, 4)
    add("fundamentals", {"symbol": "NVDA"}, 4, 4)
    add("screener", {"sector": "semiconductors"}, 6, 5)
    add("news", {"scope_type": "sector", "scope": "ai_tech"}, 6, 4)
    add("sentiment", {"scope_type": "sector", "scope": "semiconductors"}, 6, 4)
    return {
        "sessionId": "default",
        "summary": "Default desk: market heatmap, NVIDIA price and fundamentals, a semiconductor screener, AI/tech news and sector sentiment. Type a request on the right to recompose the dashboard.",
        "panels": panels,
    }


@api.get("/dashboard/default", response_model=models.DashboardSpec)
def default_dashboard():
    return _build_default_dashboard()


@api.post("/orchestrate", response_model=models.DashboardSpec)
def orchestrate(req: models.OrchestrationRequest):
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    return agent.orchestrate(req.query.strip(), req.sessionId, voice=bool(req.voice))


@api.post("/speak", response_model=models.SpeechAudio)
def speak(req: models.SpeakRequest):
    import base64

    from . import ai

    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if not ai.ai_available():
        raise HTTPException(status_code=503, detail="speech synthesis unavailable")
    try:
        audio = ai.speak(text, voice=req.voice)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"speech synthesis failed: {exc}")
    return {"audio": base64.b64encode(audio).decode("ascii"), "format": "mp3"}


@api.post("/navigate", response_model=models.NavigationTour)
def navigate(req: models.NavigateRequest):
    if not req.sessionId or not req.sessionId.strip():
        raise HTTPException(status_code=400, detail="sessionId is required")
    return agent.navigate(req.query, req.sessionId.strip())


@api.post("/refine", response_model=models.Panel)
def refine(req: models.RefineRequest):
    updated = agent.refine(req.sessionId, req.panelId, req.instruction)
    if updated is None:
        raise HTTPException(status_code=404, detail="panel not found for session")
    return updated


@api.get("/generated-panels")
def get_generated_panels():
    """Return the source of every AI-generated panel component.

    A production (built) frontend has no Vite HMR / ``import.meta.glob`` to pick
    up panels authored after the build, so it fetches their TSX source here and
    compiles them at runtime. ``panelType`` matches the file name (minus ``.tsx``).
    """
    import os

    # Infrastructure components that live alongside generated panels but are not
    # themselves AI-generated panel renderers.
    infra = {"DynamicPanel.tsx", "GeneratedPanel.tsx"}

    panels = []
    panel_dir = feature_builder.PANEL_DIR
    if os.path.isdir(panel_dir):
        for fname in sorted(os.listdir(panel_dir)):
            if not fname.endswith(".tsx") or fname.startswith("_") or fname in infra:
                continue
            panel_type = fname[: -len(".tsx")]
            try:
                with open(os.path.join(panel_dir, fname), encoding="utf-8") as fh:
                    source = fh.read()
            except OSError:
                continue
            panels.append({"panelType": panel_type, "source": source})
    return {"panels": panels}


class FeatureRequestInput(BaseModel):
    description: str


@api.post("/feature-request")
def feature_request(req: FeatureRequestInput):
    """Stream the self-building feature pipeline as Server-Sent Events.

    The sync generator runs in a threadpool; each stage is emitted as it completes.
    """
    return StreamingResponse(
        feature_builder.stream_feature_request(req.description),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _watchlist_payload() -> dict:
    items = []
    for s in state.get_watchlist():
        c = repo.get_company(s)
        if not c:
            continue
        items.append({
            "symbol": s,
            "name": c["name"],
            "price": c["price"],
            "changePct": c["changePct"],
        })
    return {"items": items}


@api.get("/watchlist", response_model=models.Watchlist)
def get_watchlist():
    return _watchlist_payload()


@api.post("/watchlist", response_model=models.Watchlist)
def add_watchlist(req: models.WatchlistInput):
    sym = req.symbol.upper()
    if not repo.get_company(sym):
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {sym}")
    state.add_watchlist(sym)
    return _watchlist_payload()


@api.delete("/watchlist/{symbol}", response_model=models.Watchlist)
def remove_watchlist(symbol: str):
    state.remove_watchlist(symbol.upper())
    return _watchlist_payload()


app.include_router(api)
