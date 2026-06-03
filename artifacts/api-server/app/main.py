"""FastAPI application for the agentic terminal. Served under the /api prefix."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import agent, data, harness, models, skills, state

app = FastAPI(title="Agentic Terminal API")

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
    return {"sectors": data.list_sectors()}


@api.get("/suggestions", response_model=models.SuggestionList)
def get_suggestions():
    return {"prompts": [
        "Give me a market overview of what's moving today",
        "Deep dive on NVIDIA",
        "Compare NVDA, AMD and TSM",
        "What's the latest news in energy?",
        "Show me the AI/tech sector heatmap",
        "Screen the semiconductor sector",
        "What's the sentiment on Palantir?",
        "Fundamentals for Exxon vs Chevron",
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
    return agent.orchestrate(req.query.strip(), req.sessionId)


@api.post("/refine", response_model=models.Panel)
def refine(req: models.RefineRequest):
    updated = agent.refine(req.sessionId, req.panelId, req.instruction)
    if updated is None:
        raise HTTPException(status_code=404, detail="panel not found for session")
    return updated


def _watchlist_payload() -> dict:
    items = []
    for s in state.get_watchlist():
        c = data.get_company(s)
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
    if not data.get_company(sym):
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {sym}")
    state.add_watchlist(sym)
    return _watchlist_payload()


@api.delete("/watchlist/{symbol}", response_model=models.Watchlist)
def remove_watchlist(symbol: str):
    state.remove_watchlist(symbol.upper())
    return _watchlist_payload()


app.include_router(api)
