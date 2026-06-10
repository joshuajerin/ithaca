"""FastAPI application for the agentic terminal. Served under the /api prefix."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import agent, alerts, auth, auth_store, dashboard_store, db, dynamic_skills, feature_builder, firm_settings, harness, models, permissions, repo, security, skills, state, tenant, worker

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

# Transport + anti-sniffing/anti-framing headers on every response, and a hard
# body-size cap. Added before CORS so they wrap every response including errors.
app.add_middleware(security.SecurityHeadersMiddleware)
app.add_middleware(security.BodySizeLimitMiddleware)

# CORS is pinned to the known terminal origin(s) instead of a wildcard, so the
# credentialed session cookie can never be replayed from an attacker origin. The
# terminal is same-origin behind the proxy, so this list is normally only the
# Replit preview/deployment host(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=security.allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

async def require_identity(
    session: str | None = Cookie(default=None, alias=auth.COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> auth.Identity:
    """Resolve the authenticated caller from the session token or 401.

    Attached to the protected API router so every business endpoint receives a
    verified ``{user, firm, role}`` identity. Logged-out callers (no/invalid/
    expired token) are rejected before any handler runs.

    Browsers send the session as the httpOnly ``at_session`` cookie. Non-browser
    clients (and test harnesses, which have no cookie jar) may instead present
    the same session token as an ``Authorization: Bearer <token>`` header — the
    generated API client already attaches it this way when a token getter is set.
    The cookie takes precedence; both resolve through the same session lookup.
    """
    token = session
    if not token and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            token = value.strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = auth_store.get_session_user_id(auth.hash_token(token))
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = auth_store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    firm = auth_store.get_firm(user["firmId"])
    # Bind the firm for the rest of this request so every store call (however deep)
    # scopes reads and stamps writes to this tenant. Set in an async dependency so
    # the value propagates into the threadpool that runs sync handlers.
    tenant.set_current_firm(user["firmId"])
    return auth.Identity(
        user_id=user["id"],
        firm_id=user["firmId"],
        role=user["role"],
        name=user["name"],
        email=user["email"],
        firm_name=firm["name"] if firm else "",
    )


def require_role(*roles: str):
    """Dependency factory: require the caller hold one of ``roles``.

    Builds on :func:`require_identity` (so it also enforces authentication) and
    returns the resolved identity, letting privileged handlers gate by role. The
    role check is server-side and authoritative — the frontend hiding a control
    is convenience only.

    Prefer :func:`require_permission` for action-level gating routed through the
    authoritative permission matrix; ``require_role`` remains for coarse checks
    (e.g. the firm-admin-only settings/kill-switch surface).
    """
    allowed = frozenset(roles)

    def dependency(identity: auth.Identity = Depends(require_identity)) -> auth.Identity:
        if identity.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )
        return identity

    return dependency


def require_codegen_enabled(
    identity: auth.Identity = Depends(require_role("admin")),
) -> auth.Identity:
    """Gate AI code-execution (build) endpoints: admin role + firm not opted out.

    Combines the role check with the per-firm code-execution kill-switch so a
    firm admin can disable the self-building pipeline for their whole firm.
    """
    if not firm_settings.codegen_enabled(identity.firm_id):
        raise HTTPException(
            status_code=403,
            detail="AI feature building is disabled for your firm.",
        )
    return identity


def require_permission(action: str):
    """Build a dependency that asserts the caller's role may perform ``action``.

    Authorization is authoritative on the server: every sensitive/mutating route
    declares the action it represents, and this dependency rejects any caller
    whose role is below that action's minimum (per ``permissions.ACTIONS``) with
    a clear 403 — even if the request is hand-crafted to bypass the UI.

    It re-uses ``require_identity`` (FastAPI caches it within the request, so the
    session is resolved only once) and returns the verified identity so handlers
    can still depend on it.
    """

    def _dep(identity: auth.Identity = Depends(require_identity)) -> auth.Identity:
        if not permissions.can(identity.role, action):
            raise HTTPException(
                status_code=403,
                detail=permissions.denial_message(identity.role, action),
            )
        return identity

    return _dep


# Public router — no authentication required (health check + the auth flow
# itself). Kept separate from the protected `api` router below so logged-out
# users can reach signup/login without already holding a session.
public = APIRouter(prefix="/api")

# Protected router — every route gets the identity dependency, so the whole
# business API requires a valid session and resolves {user, firm, role}.
api = APIRouter(prefix="/api", dependencies=[Depends(require_identity)])


@public.get("/healthz")
def healthz():
    from . import ai
    return {"status": "ok", "aiAvailable": ai.ai_available()}


@public.get("/readyz")
def readyz(response: Response):
    """Readiness probe for horizontal scale.

    Reports whether this instance can serve durable, shared state: when a
    database is configured we ping it (and surface pool telemetry). If the DB is
    configured but unreachable the instance is *not* ready for the durability
    promise, so we return 503 so the platform can route around it. When no DB is
    configured the app runs in its in-memory fallback mode and is considered
    ready (it serves, it just isn't durable).
    """
    from . import ai

    db_configured = db.db_available()
    db_ok = db.ping() if db_configured else False
    ready = db_ok or not db_configured
    if not ready:
        response.status_code = 503
    return {
        "status": "ready" if ready else "degraded",
        "db": {"configured": db_configured, "ok": db_ok, "pool": db.pool_stats()},
        "aiAvailable": ai.ai_available(),
    }


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=auth.COOKIE_NAME,
        value=token,
        max_age=auth.SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@public.post(
    "/auth/signup",
    response_model=models.AuthIdentity,
    dependencies=[Depends(security.rate_limit("auth", 10, 60))],
)
def auth_signup(req: models.SignupRequest, response: Response):
    """Create a firm and its first (admin) user, then start a session."""
    firm_name = (req.firmName or "").strip()
    name = (req.name or "").strip()
    email = auth.normalize_email(req.email)
    password = req.password or ""
    if not firm_name or not name or not email or not password:
        raise HTTPException(status_code=400, detail="All fields are required")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if auth_store.email_exists(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    firm = auth_store.create_firm(firm_name)
    pw_hash, pw_salt = auth.hash_password(password)
    # The first user of a firm is its admin.
    user = auth_store.create_user(
        firm_id=firm["id"],
        email=email,
        name=name,
        role="admin",
        password_hash=pw_hash,
        password_salt=pw_salt,
    )
    token = auth.new_session_token()
    auth_store.create_session(auth.hash_token(token), user["id"], auth.SESSION_TTL_SECONDS)
    _set_session_cookie(response, token)
    return {
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
        "firm": {"id": firm["id"], "name": firm["name"]},
        "permissions": permissions.allowed_actions(user["role"]),
    }


@public.post(
    "/auth/login",
    response_model=models.AuthIdentity,
    dependencies=[Depends(security.rate_limit("auth", 10, 60))],
)
def auth_login(req: models.LoginRequest, response: Response):
    """Verify credentials and start a durable session."""
    email = auth.normalize_email(req.email)
    password = req.password or ""
    user = auth_store.get_user_by_email(email)
    if not user or not auth.verify_password(password, user["passwordHash"], user["passwordSalt"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    firm = auth_store.get_firm(user["firmId"])
    token = auth.new_session_token()
    auth_store.create_session(auth.hash_token(token), user["id"], auth.SESSION_TTL_SECONDS)
    _set_session_cookie(response, token)
    return {
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
        "firm": {"id": firm["id"], "name": firm["name"]} if firm else {"id": user["firmId"], "name": ""},
        "permissions": permissions.allowed_actions(user["role"]),
    }


@public.post("/auth/logout", response_model=models.LogoutResult)
def auth_logout(
    response: Response,
    session: str | None = Cookie(default=None, alias=auth.COOKIE_NAME),
):
    """Invalidate the current session and clear the cookie."""
    if session:
        auth_store.delete_session(auth.hash_token(session))
    response.delete_cookie(key=auth.COOKIE_NAME, path="/")
    return {"ok": True}


@public.get("/auth/user", response_model=models.AuthIdentity)
def auth_user(identity: auth.Identity = Depends(require_identity)):
    """Return the current user/firm/role, or 401 when not authenticated."""
    return identity.to_payload()


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
        "Compare the risk of NVDA, MSFT, GOOGL vs JPM, XOM, JNJ side by side",
        "Is a tech portfolio riskier or better diversified than a defensive one?",
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


@api.post(
    "/orchestrate",
    response_model=models.DashboardSpec,
    dependencies=[Depends(security.rate_limit("orchestrate", 30, 60))],
)
def orchestrate(
    req: models.OrchestrationRequest,
    identity: auth.Identity = Depends(require_identity),
):
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    result = agent.orchestrate(req.query.strip(), req.sessionId, voice=bool(req.voice))
    # Tie this session to the authenticated user/firm (foundation for isolation).
    sid = result.get("sessionId") if isinstance(result, dict) else None
    if sid:
        state.set_session_owner(sid, identity.user_id, identity.firm_id)
    return result


@api.get("/dashboards", response_model=models.SavedDashboardList)
def list_saved_dashboards():
    return {"dashboards": dashboard_store.list_dashboards()}


@api.post(
    "/dashboards",
    response_model=models.SavedDashboardMeta,
    dependencies=[Depends(require_permission("dashboard.save"))],
)
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


@api.delete(
    "/dashboards/{dashboard_id}",
    response_model=models.SavedDashboardList,
    dependencies=[Depends(require_permission("dashboard.delete"))],
)
def delete_saved_dashboard(dashboard_id: str):
    dashboard_store.delete_dashboard(dashboard_id)
    return {"dashboards": dashboard_store.list_dashboards()}


@api.post(
    "/orchestrate/stream",
    dependencies=[Depends(security.rate_limit("orchestrate", 30, 60))],
)
def orchestrate_stream(
    req: models.OrchestrationRequest,
    identity: auth.Identity = Depends(require_identity),
):
    """Stream a Console reply as Server-Sent Events.

    A conversational *question* streams as ``{"type":"delta","text":...}`` events
    so the answer renders word-by-word; the final ``{"type":"done","result":...}``
    event carries the full DashboardSpec-shaped payload. A build request emits only
    the ``done`` event (panels, not prose). The client falls back to the blocking
    ``/orchestrate`` endpoint if anything goes wrong.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    def gen():
        try:
            for event in agent.orchestrate_stream(
                req.query.strip(), req.sessionId, voice=bool(req.voice)
            ):
                # Tie the session to the authenticated user/firm once its id is known.
                if isinstance(event, dict) and event.get("type") == "done":
                    result = event.get("result") or {}
                    sid = result.get("sessionId")
                    if sid:
                        state.set_session_owner(sid, identity.user_id, identity.firm_id)
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post(
    "/speak",
    response_model=models.SpeechAudio,
    dependencies=[Depends(security.rate_limit("speak", 60, 60))],
)
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


@api.post(
    "/transcribe",
    response_model=models.Transcription,
    dependencies=[Depends(security.rate_limit("transcribe", 60, 60))],
)
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
        return skills.recompute_scenario(req.symbols, req.horizonDays, req.driftPct, req.amount)
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


@api.post("/strategies", dependencies=[Depends(require_permission("strategy.manage"))])
def create_strategy(req: StrategyCreateRequest):
    from . import strategy
    try:
        view = strategy.create_strategy(
            name=req.name, signal=req.signal, symbols=req.symbols, weights=req.weights,
            sector=req.sector, capital=req.capital, promotion_criteria=req.promotionCriteria,
            notes=req.notes, paper=req.paper,
        )
    except strategy.ComplianceBlock as cb:
        # The strategy was created in research but the paper book it would have
        # opened is refused by the pre-trade gate. Surface the reason, not a 500.
        return {"ok": False, "blocked": True, "reason": cb.result.get("reason"),
                "compliance": cb.result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not create strategy: {exc}")
    return view


@api.post(
    "/strategies/{strategy_id}/transition",
    dependencies=[Depends(require_permission("strategy.manage"))],
)
def transition_strategy(strategy_id: str, req: StrategyTransitionRequest):
    from . import strategy, strategy_store
    view = strategy_store.get_strategy(strategy_id)
    if view is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    stage = (req.stage or "").strip().lower()
    try:
        if stage == "demote":
            updated, ok, message = strategy.demote(view)
        else:
            updated, ok, message = strategy.transition(view, stage, force=req.force)
    except strategy.ComplianceBlock as cb:
        return {"ok": False, "blocked": True, "message": cb.result.get("reason"),
                "compliance": cb.result, "strategy": view}
    return {"ok": ok, "message": message, "strategy": updated}


@api.post(
    "/strategies/{strategy_id}/rebalance",
    dependencies=[Depends(require_permission("strategy.trade"))],
)
def rebalance_strategy(strategy_id: str, req: StrategyRebalanceRequest | None = None):
    from . import strategy, strategy_store
    view = strategy_store.get_strategy(strategy_id)
    if view is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    cost_bps = (req.costBps if req and req.costBps is not None else strategy.DEFAULT_COST_BPS)
    updated, info = strategy.rebalance(view, cost_bps=cost_bps)
    return {"ok": bool(info.get("applied")), "rebalance": info, "strategy": updated}


# ------------------------------ strategy templates marketplace ----------------
class TemplateConfig(BaseModel):
    id: str | None = None
    templateId: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    signal: str | None = None
    sector: str | None = None
    topN: int | None = None
    capital: float | None = None


@api.get("/templates")
def list_templates():
    from . import templates
    return {"templates": templates.list_all()}


@api.post("/templates/clone", dependencies=[Depends(require_permission("template.use"))])
def clone_template(req: TemplateConfig):
    """Clone a configured template into the paper-trading desk."""
    from . import strategy, templates
    cfg = templates.resolve_config(req.model_dump(exclude_none=True))
    try:
        view = templates.clone(cfg)
    except strategy.ComplianceBlock as cb:
        return {"ok": False, "blocked": True, "reason": cb.result.get("reason"),
                "compliance": cb.result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not clone template: {exc}")
    return {"ok": True, "strategy": view}


@api.post("/templates", dependencies=[Depends(require_permission("template.use"))])
def save_template(req: TemplateConfig):
    """Save a user-configured template as a reusable preset."""
    from . import templates
    cfg = templates.resolve_config(req.model_dump(exclude_none=True))
    try:
        saved = templates.save(cfg)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not save template: {exc}")
    return {"ok": True, "template": saved, "templates": templates.list_all()}


@api.delete(
    "/templates/{template_id}",
    dependencies=[Depends(require_permission("template.use"))],
)
def delete_template(template_id: str):
    from . import templates, template_store
    if not template_id.startswith("user-"):
        raise HTTPException(status_code=400, detail="only your saved templates can be deleted")
    removed = template_store.delete(template_id)
    if not removed:
        raise HTTPException(status_code=404, detail="template not found")
    return {"ok": True, "templates": templates.list_all()}


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


@api.delete(
    "/features/{panel_type}",
    dependencies=[Depends(require_permission("feature.build"))],
)
def delete_feature(
    panel_type: str,
    _identity: auth.Identity = Depends(require_role("admin")),
):
    """Remove a generated feature: unregister it and delete its source files.

    Restricted to firm admins — generated features are shared in-process, so
    removing one affects every user; only an admin may do it. The
    ``feature.build`` permission (admin-only in the matrix) is also enforced so
    the action is routed through the single authoritative permission matrix.
    """
    removed = feature_builder.remove_feature(panel_type)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Unknown feature: {panel_type}")
    return {"ok": True, "panelType": panel_type}


# ------------------------------ firm settings --------------------------------
class FirmCodegenInput(BaseModel):
    codegenEnabled: bool


@api.get("/firm/settings")
def get_firm_settings(identity: auth.Identity = Depends(require_identity)):
    """Return the firm's security settings (e.g. the code-execution toggle).

    Readable by any member so the UI can hide the build affordance; only an admin
    may change it (see the POST below).
    """
    settings = firm_settings.get_settings(identity.firm_id)
    return {**settings, "canManage": identity.role == "admin"}


@api.post("/firm/settings")
def update_firm_settings(
    req: FirmCodegenInput,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Admin-only: toggle the AI code-execution (feature-building) kill-switch."""
    settings = firm_settings.set_codegen_enabled(identity.firm_id, req.codegenEnabled)
    return {**settings, "canManage": True}


class FeatureRequestInput(BaseModel):
    description: str


# The single highest-risk surface: an admin describes a feature and the AI
# authors + executes new code. Gated by the admin-only ``feature.build``
# permission (authoritative matrix) plus the per-firm code-execution kill-switch
# (require_codegen_enabled), and rate-limited at the edge (the builder also
# enforces its own concurrency/rate limits and validates every generation before
# execution).
@api.post(
    "/feature-request",
    dependencies=[
        Depends(require_permission("feature.build")),
        Depends(security.rate_limit("feature-request", 10, 60)),
    ],
)
def feature_request(
    req: FeatureRequestInput,
    _identity: auth.Identity = Depends(require_codegen_enabled),
):
    """Stream the self-building feature pipeline as Server-Sent Events.

    The sync generator runs in a threadpool; each stage is emitted as it completes.
    """
    description = (req.description or "").strip()
    if len(description) > 2000:
        raise HTTPException(status_code=400, detail="description is too long")
    return StreamingResponse(
        feature_builder.stream_feature_request(description),
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


@api.post("/dcf-models", dependencies=[Depends(require_permission("dcf.save"))])
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


@api.delete("/dcf-models", dependencies=[Depends(require_permission("dcf.save"))])
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


@api.post(
    "/watchlist",
    response_model=models.Watchlist,
    dependencies=[Depends(require_permission("watchlist.edit"))],
)
def add_watchlist(req: models.WatchlistInput):
    sym = req.symbol.upper()
    if not repo.get_company(sym):
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {sym}")
    state.add_watchlist(sym)
    return _watchlist_payload()


@api.delete(
    "/watchlist/{symbol}",
    response_model=models.Watchlist,
    dependencies=[Depends(require_permission("watchlist.edit"))],
)
def remove_watchlist(symbol: str):
    state.remove_watchlist(symbol.upper())
    return _watchlist_payload()


# ------------------------------ trade-flow alerts ----------------------------
class AlertRuleInput(BaseModel):
    sessionId: str
    symbol: str
    metric: str
    threshold: float


def _alerts_payload(session_id: str) -> dict:
    return {
        "rules": state.get_alert_rules(session_id),
        "events": list(reversed(state.get_alert_events(session_id))),
        "metrics": alerts.METRICS,
    }


@api.get("/alerts")
def get_alerts(sessionId: str):
    if not sessionId or not sessionId.strip():
        raise HTTPException(status_code=400, detail="sessionId is required")
    return _alerts_payload(sessionId.strip())


@api.post("/alerts", dependencies=[Depends(require_permission("alert.manage"))])
def create_alert(req: AlertRuleInput):
    sid = (req.sessionId or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="sessionId is required")
    if not repo.get_company(req.symbol.upper()):
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {req.symbol}")
    try:
        rule = alerts.normalize_rule(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    state.add_alert_rule(sid, rule)
    # Evaluate immediately against the current trade-flow panels so a matching
    # rule fires right away rather than waiting for the next build.
    alerts.evaluate_dashboard(sid, state.get_dashboard(sid))
    return _alerts_payload(sid)


# NOTE: the static "/alerts/events" routes MUST be declared before the
# parametrized "/alerts/{rule_id}" route, otherwise FastAPI matches "events" as a
# rule_id and the event GET/DELETE never run.
@api.get("/alerts/events")
def get_alert_events(sessionId: str):
    if not sessionId or not sessionId.strip():
        raise HTTPException(status_code=400, detail="sessionId is required")
    return {"events": list(reversed(state.get_alert_events(sessionId.strip())))}


@api.delete("/alerts/events", dependencies=[Depends(require_permission("alert.manage"))])
def clear_alert_events(sessionId: str):
    if not sessionId or not sessionId.strip():
        raise HTTPException(status_code=400, detail="sessionId is required")
    state.clear_alert_events(sessionId.strip())
    return {"events": []}


@api.delete("/alerts/{rule_id}", dependencies=[Depends(require_permission("alert.manage"))])
def delete_alert(rule_id: str, sessionId: str):
    sid = (sessionId or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="sessionId is required")
    state.remove_alert_rule(sid, rule_id)
    return _alerts_payload(sid)


# --------------------------- pre-trade compliance ----------------------------
class ComplianceSymbolInput(BaseModel):
    symbol: str


class ComplianceLimitsInput(BaseModel):
    limits: dict


class ComplianceKillSwitchInput(BaseModel):
    on: bool
    reason: str | None = None
    strategyId: str | None = None


def _compliance_payload(strategy: str | None = None) -> dict:
    from . import skills
    return skills.build_compliance({"strategy": strategy} if strategy else {})


@api.get("/compliance")
def get_compliance(strategy: str | None = None):
    return _compliance_payload(strategy)


@api.post("/compliance/restricted", dependencies=[Depends(require_permission("compliance.config"))])
def add_restricted(req: ComplianceSymbolInput):
    from . import compliance_store
    sym = (req.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")
    compliance_store.add_restricted(sym)
    return _compliance_payload()


@api.post("/compliance/watch", dependencies=[Depends(require_permission("compliance.config"))])
def add_watch(req: ComplianceSymbolInput):
    from . import compliance_store
    sym = (req.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")
    compliance_store.add_watch(sym)
    return _compliance_payload()


@api.post("/compliance/limits", dependencies=[Depends(require_permission("compliance.config"))])
def set_limits(req: ComplianceLimitsInput):
    from . import compliance_store
    compliance_store.set_limits(req.limits or {})
    return _compliance_payload()


@api.post("/compliance/kill-switch", dependencies=[Depends(require_permission("compliance.config"))])
def set_kill_switch(req: ComplianceKillSwitchInput):
    from . import compliance_store
    compliance_store.set_kill_switch(bool(req.on), reason=req.reason, strategy_id=req.strategyId)
    return _compliance_payload()


@api.post("/compliance/check")
def check_compliance(req: ComplianceSymbolInput):
    # ``symbol`` here is reused as the strategy name/id to pre-check.
    sel = (req.symbol or "").strip()
    if not sel:
        raise HTTPException(status_code=400, detail="strategy is required")
    return _compliance_payload(sel)


@api.delete("/compliance/audit", dependencies=[Depends(require_permission("compliance.config"))])
def clear_compliance_audit():
    from . import compliance_store
    n = compliance_store.clear_audit()
    return {"cleared": n}


# NOTE: the parametrized "/compliance/{list}/{symbol}" DELETE routes are declared
# AFTER every static "/compliance/..." route above so FastAPI does not match e.g.
# "limits" as a {symbol}.
@api.delete("/compliance/restricted/{symbol}", dependencies=[Depends(require_permission("compliance.config"))])
def remove_restricted(symbol: str):
    from . import compliance_store
    compliance_store.remove_restricted(symbol.upper())
    return _compliance_payload()


@api.delete("/compliance/watch/{symbol}", dependencies=[Depends(require_permission("compliance.config"))])
def remove_watch(symbol: str):
    from . import compliance_store
    compliance_store.remove_watch(symbol.upper())
    return _compliance_payload()


app.include_router(public)
app.include_router(api)
