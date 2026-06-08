"""FastAPI application for the agentic terminal. Served under the /api prefix."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import agent, dashboard_store, dynamic_skills, feature_builder, harness, models, repo, skills, state, worker

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
        "What is a Sortino ratio?",
        "Deep dive on NVIDIA",
        "Explain what I'm seeing on this dashboard",
        "Compare NVDA, AMD and TSM",
        "What's the difference between IV and HV?",
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


@api.get("/dashboards", response_model=models.SavedDashboardList)
def list_saved_dashboards():
    return {"dashboards": dashboard_store.list_dashboards()}


@api.post("/dashboards", response_model=models.SavedDashboardMeta)
def save_dashboard(req: models.SaveDashboardRequest):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not req.panels:
        raise HTTPException(status_code=400, detail="cannot save an empty dashboard")
    panels = [p.model_dump() for p in req.panels]
    record = dashboard_store.save_dashboard(name, req.summary or "", panels)
    return {
        "id": record["id"],
        "name": record["name"],
        "summary": record.get("summary") or "",
        "panelCount": len(record.get("panels") or []),
        "createdAt": record.get("createdAt"),
        "updatedAt": record.get("updatedAt"),
    }


@api.get("/dashboards/{dashboard_id}", response_model=models.DashboardSpec)
def restore_dashboard(dashboard_id: str):
    """Load a saved dashboard into a fresh session and return its full spec so
    the terminal can render it and keep refining from there."""
    import uuid

    record = dashboard_store.get_dashboard(dashboard_id)
    if record is None:
        raise HTTPException(status_code=404, detail="saved dashboard not found")
    panels = record.get("panels") or []
    sid = uuid.uuid4().hex[:12]
    state.set_dashboard(sid, panels)
    return {
        "sessionId": sid,
        "summary": record.get("summary") or f"Restored \u201c{record['name']}\u201d.",
        "panels": panels,
        "intent": "build",
    }


@api.delete("/dashboards/{dashboard_id}", response_model=models.SavedDashboardList)
def delete_saved_dashboard(dashboard_id: str):
    dashboard_store.delete_dashboard(dashboard_id)
    return {"dashboards": dashboard_store.list_dashboards()}


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
        audio = ai.speak(text, voice=req.voice, speed=req.speed)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"speech synthesis failed: {exc}")
    return {"audio": base64.b64encode(audio).decode("ascii"), "format": "mp3"}


def _filename_for_mime(mime: str | None) -> str:
    m = (mime or "").split(";")[0].strip().lower()
    ext = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp4": "mp4",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/aac": "aac",
        "audio/m4a": "m4a",
        "audio/x-m4a": "m4a",
    }.get(m, "webm")
    return f"audio.{ext}"


@api.post("/transcribe", response_model=models.Transcription)
def transcribe(req: models.TranscribeRequest):
    import base64
    import binascii

    from . import ai

    if not req.audio:
        raise HTTPException(status_code=400, detail="audio is required")
    try:
        audio_bytes = base64.b64decode(req.audio)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="audio must be base64-encoded")
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="audio is empty")
    if not ai.ai_available():
        raise HTTPException(status_code=503, detail="speech recognition unavailable")
    try:
        text = ai.transcribe(audio_bytes, filename=_filename_for_mime(req.mimeType))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"transcription failed: {exc}")
    return {"text": text}


@api.post("/navigate", response_model=models.NavigationTour)
def navigate(req: models.NavigateRequest):
    if not req.sessionId or not req.sessionId.strip():
        raise HTTPException(status_code=400, detail="sessionId is required")
    return agent.navigate(req.query, req.sessionId.strip())


@api.post("/refine", response_model=models.Panel)
def refine(req: models.RefineRequest):
    updated = agent.refine(req.sessionId, req.panelId, req.instruction, req.params)
    if updated is None:
        raise HTTPException(status_code=404, detail="panel not found for session")
    return updated


@api.post("/scenario/recompute", response_model=models.ScenarioRecomputeResult)
def scenario_recompute(req: models.ScenarioRecomputeRequest):
    try:
        return skills.recompute_scenario(req.symbols, req.horizonDays, req.driftPct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class StrategyCreateRequest(BaseModel):
    name: str | None = None
    signal: str | None = None
    symbols: list[str] | None = None
    weights: list[float] | None = None
    sector: str | None = None
    capital: float | None = None
    promotionCriteria: dict | None = None
    notes: str | None = None
    paper: bool = False


class StrategyTransitionRequest(BaseModel):
    stage: str
    force: bool = False


class StrategyRebalanceRequest(BaseModel):
    costBps: float | None = None


@api.get("/strategies")
def list_strategies():
    from . import strategy
    return strategy.desk_payload()


@api.post("/strategies")
def create_strategy(req: StrategyCreateRequest):
    from . import strategy
    try:
        view = strategy.create_strategy(
            name=req.name, signal=req.signal, symbols=req.symbols, weights=req.weights,
            sector=req.sector, capital=req.capital, promotion_criteria=req.promotionCriteria,
            notes=req.notes, paper=req.paper,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not create strategy: {exc}")
    return view


@api.post("/strategies/{strategy_id}/transition")
def transition_strategy(strategy_id: str, req: StrategyTransitionRequest):
    from . import strategy, strategy_store
    view = strategy_store.get_strategy(strategy_id)
    if view is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    stage = (req.stage or "").strip().lower()
    if stage == "demote":
        updated, ok, message = strategy.demote(view)
    else:
        updated, ok, message = strategy.transition(view, stage, force=req.force)
    return {"ok": ok, "message": message, "strategy": updated}


@api.post("/strategies/{strategy_id}/rebalance")
def rebalance_strategy(strategy_id: str, req: StrategyRebalanceRequest | None = None):
    from . import strategy, strategy_store
    view = strategy_store.get_strategy(strategy_id)
    if view is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    cost_bps = (req.costBps if req and req.costBps is not None else strategy.DEFAULT_COST_BPS)
    updated, info = strategy.rebalance(view, cost_bps=cost_bps)
    return {"ok": bool(info.get("applied")), "rebalance": info, "strategy": updated}


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


@api.get("/features")
def list_features():
    """List every active AI-generated feature (name, invoke example, created date)."""
    return {"features": feature_builder.list_features()}


@api.delete("/features/{panel_type}")
def delete_feature(panel_type: str):
    """Remove a generated feature: unregister it and delete its source files."""
    removed = feature_builder.remove_feature(panel_type)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Unknown feature: {panel_type}")
    return {"ok": True, "panelType": panel_type}


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


class DCFModelInput(BaseModel):
    sessionId: str
    name: str
    symbol: str
    assumptions: dict


@api.get("/dcf-models")
def list_dcf_models(sessionId: str, symbol: str | None = None):
    if not sessionId or not sessionId.strip():
        raise HTTPException(status_code=400, detail="sessionId is required")
    return {"models": state.list_dcf_models(sessionId.strip(), symbol)}


@api.post("/dcf-models")
def save_dcf_model(req: DCFModelInput):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not req.sessionId or not req.sessionId.strip():
        raise HTTPException(status_code=400, detail="sessionId is required")
    if not req.symbol or not req.symbol.strip():
        raise HTTPException(status_code=400, detail="symbol is required")
    required = {"revenueGrowth", "ebitdaMargin", "wacc", "exitMultiple", "taxRate", "capexPct"}
    missing = required - set(req.assumptions.keys())
    if missing:
        raise HTTPException(status_code=400, detail=f"assumptions missing keys: {sorted(missing)}")
    models = state.save_dcf_model(req.sessionId.strip(), name, req.symbol.strip(), req.assumptions)
    return {"models": models}


@api.delete("/dcf-models")
def delete_dcf_model(sessionId: str, name: str, symbol: str):
    if not sessionId or not sessionId.strip():
        raise HTTPException(status_code=400, detail="sessionId is required")
    models = state.delete_dcf_model(sessionId.strip(), name, symbol)
    return {"models": models}


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
