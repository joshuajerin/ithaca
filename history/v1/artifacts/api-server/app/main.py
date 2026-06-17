"""FastAPI application for the agentic terminal. Served under the /api prefix."""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import agent, alerts, auth, auth_store, cache, dashboard_store, db, dynamic_skills, feature_builder, firm_settings, harness, models, permissions, repo, security, skills, state, tenant, worker

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
    # A deactivated user keeps their account & history but may not authenticate.
    # Their sessions are normally revoked at deactivation; this is the durable
    # backstop so any lingering token is rejected too.
    if not user.get("active", True):
        raise HTTPException(status_code=401, detail="Your account has been deactivated.")
    firm = auth_store.get_firm(user["firmId"])
    # Bind the firm for the rest of this request so every store call (however deep)
    # scopes reads and stamps writes to this tenant. Set in an async dependency so
    # the value propagates into the threadpool that runs sync handlers.
    tenant.set_current_firm(user["firmId"])
    # Bind the acting user too, so every audit write (including the deep pre-trade
    # gate) attributes to a real person without threading the id through.
    tenant.set_current_actor(user["id"], user.get("name"), user.get("email"))
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
            # Record the denied attempt before refusing — it is exactly the kind of
            # event the audit trail exists to capture. The firm + actor context is
            # already bound by require_identity, so the entry is attributed.
            from . import compliance_store
            compliance_store.append_audit(
                category="auth",
                action="permission_denied",
                summary=f"Denied: requires {', '.join(sorted(allowed))} (role: {identity.role})",
                decision="blocked",
            )
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
            # Record the denied attempt before refusing — capturing permission
            # denials is exactly what the audit trail exists for. The firm + actor
            # context is already bound by require_identity, so it is attributed.
            from . import compliance_store
            compliance_store.append_audit(
                category="auth",
                action="permission_denied",
                target=action,
                summary=f"Denied: requires permission “{action}” (role: {identity.role})",
                decision="blocked",
            )
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
    _audit_auth(firm["id"], user, "signup", f"{user['name']} created firm “{firm['name']}”")
    return {
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
        "firm": {"id": firm["id"], "name": firm["name"]},
        "permissions": permissions.allowed_actions(user["role"]),
    }


def _audit_auth(firm_id: str, user: dict | None, action: str, summary: str, decision: str | None = None) -> None:
    """Record an auth event on the public router, where no identity dependency has
    bound the firm/actor context yet — so pass both explicitly."""
    from . import compliance_store
    compliance_store.append_audit(
        firm_id=firm_id,
        actor_user_id=(user or {}).get("id"),
        actor_name=(user or {}).get("name"),
        category="auth",
        action=action,
        summary=summary,
        target=(user or {}).get("email"),
        decision=decision,
    )


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
        # A failed login against a known account is auditable; an unknown email has
        # no firm to scope the entry to, so it is not recorded.
        if user:
            _audit_auth(user["firmId"], user, "login_failed",
                        f"Failed login for {user['name']}", decision="blocked")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Your account has been deactivated.")
    firm = auth_store.get_firm(user["firmId"])
    token = auth.new_session_token()
    auth_store.create_session(auth.hash_token(token), user["id"], auth.SESSION_TTL_SECONDS)
    _set_session_cookie(response, token)
    _audit_auth(user["firmId"], user, "login", f"{user['name']} signed in")
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
        # Resolve the user from the session before deleting it so the logout is
        # attributed (the public router binds no identity context).
        user_id = auth_store.get_session_user_id(auth.hash_token(session))
        user = auth_store.get_user_by_id(user_id) if user_id else None
        if user:
            _audit_auth(user["firmId"], user, "logout", f"{user['name']} signed out")
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


# The default dashboard is identical for every user (no params, no user/firm
# scoping) yet each build fires several live upstream fetches (heatmap, news,
# sentiment) and emits a ~240KB payload, so it costs ~1s of work per request.
# Under concurrency it saturates the single worker and drags every other
# endpoint down. Because the result is the same for everyone, we serve it from a
# short-TTL process cache so the live fetches happen at most once per window
# instead of once per request. TTL is env-tunable (0 disables caching).
_DEFAULT_DASHBOARD_TTL = float(os.environ.get("DASHBOARD_DEFAULT_TTL", "60"))


@api.get("/dashboard/default", response_model=models.DashboardSpec)
def default_dashboard():
    if _DEFAULT_DASHBOARD_TTL <= 0:
        return _build_default_dashboard()
    # Single-flight: when the TTL lapses, only one request rebuilds (with its
    # live upstream fetches) while concurrent callers wait and read the fresh
    # value, instead of a thundering herd of simultaneous expensive builds.
    return cache.cached_singleflight(
        "dashboard:default", _DEFAULT_DASHBOARD_TTL, _build_default_dashboard
    )


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
    from . import compliance_store
    compliance_store.append_audit(
        category="dashboard", action="dashboard.save", target=record["name"],
        summary=f"Saved dashboard “{record['name']}” ({len(panels)} panels)",
    )
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
    record = dashboard_store.get_dashboard(dashboard_id)
    dashboard_store.delete_dashboard(dashboard_id)
    from . import compliance_store
    compliance_store.append_audit(
        category="dashboard", action="dashboard.delete",
        target=(record or {}).get("name") or dashboard_id,
        summary=f"Deleted dashboard “{(record or {}).get('name') or dashboard_id}”",
    )
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
    from . import compliance_store
    compliance_store.append_audit(
        category="strategy", action="strategy.create",
        target=view.get("name"), strategy_id=view.get("id"), strategy_name=view.get("name"),
        summary=f"Created strategy “{view.get('name')}” in {view.get('stage')}",
    )
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
    if ok:
        from . import compliance_store
        compliance_store.append_audit(
            category="strategy", action="strategy.transition",
            target=updated.get("name"), strategy_id=updated.get("id"),
            strategy_name=updated.get("name"), summary=message,
            detail={"toStage": updated.get("stage"), "force": req.force},
        )
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
    from . import compliance_store
    applied = bool(info.get("applied"))
    compliance_store.append_audit(
        category="trade", action="strategy.rebalance",
        target=updated.get("name"), strategy_id=updated.get("id"),
        strategy_name=updated.get("name"),
        summary=(f"Rebalanced “{updated.get('name')}”: {info.get('trades')} trades, "
                 f"{info.get('turnoverPct')}% turnover" if applied
                 else f"Rebalance of “{updated.get('name')}” made no changes"),
        detail={"trades": info.get("trades"), "turnoverPct": info.get("turnoverPct"),
                "costUsd": info.get("costUsd"), "applied": applied},
    )
    return {"ok": applied, "rebalance": info, "strategy": updated}


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
    from . import compliance_store
    compliance_store.append_audit(
        category="feature", action="feature.delete", target=panel_type,
        summary=f"Removed generated feature “{panel_type}”",
    )
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
    from . import compliance_store
    compliance_store.append_audit(
        category="admin", action="firm.codegen_toggle",
        summary=f"AI feature-building {'enabled' if req.codegenEnabled else 'disabled'} firm-wide",
    )
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
    from . import compliance_store
    compliance_store.append_audit(
        category="feature", action="feature.build",
        target=(description[:60] + "…") if len(description) > 60 else description,
        summary=f"Requested AI feature build: {description[:140]}",
    )
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
    from . import compliance_store
    compliance_store.append_audit(
        category="alert", action="alert.create", target=rule.get("symbol"),
        summary=f"Created alert: {rule.get('symbol')} {rule.get('metric')} ≥ {rule.get('threshold')}",
        detail={"rule": rule},
    )
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
    rule = next((r for r in state.get_alert_rules(sid) if r.get("id") == rule_id), None)
    state.remove_alert_rule(sid, rule_id)
    from . import compliance_store
    compliance_store.append_audit(
        category="alert", action="alert.delete",
        target=(rule or {}).get("symbol") or rule_id,
        summary=(f"Deleted alert: {rule['symbol']} {rule['metric']} ≥ {rule['threshold']}"
                 if rule else f"Deleted alert {rule_id}"),
    )
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
    compliance_store.append_audit(
        category="config", action="compliance.restrict_add", target=sym,
        summary=f"Added {sym} to the restricted list",
    )
    return _compliance_payload()


@api.post("/compliance/watch", dependencies=[Depends(require_permission("compliance.config"))])
def add_watch(req: ComplianceSymbolInput):
    from . import compliance_store
    sym = (req.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")
    compliance_store.add_watch(sym)
    compliance_store.append_audit(
        category="config", action="compliance.watch_add", target=sym,
        summary=f"Added {sym} to the watch list",
    )
    return _compliance_payload()


@api.post("/compliance/limits", dependencies=[Depends(require_permission("compliance.config"))])
def set_limits(req: ComplianceLimitsInput):
    from . import compliance_store
    compliance_store.set_limits(req.limits or {})
    compliance_store.append_audit(
        category="config", action="compliance.set_limits",
        summary=f"Updated position limits: {req.limits or {}}",
        detail={"limits": req.limits or {}},
    )
    return _compliance_payload()


@api.post("/compliance/kill-switch", dependencies=[Depends(require_permission("compliance.config"))])
def set_kill_switch(req: ComplianceKillSwitchInput):
    from . import compliance_store
    compliance_store.set_kill_switch(bool(req.on), reason=req.reason, strategy_id=req.strategyId)
    scope = f"strategy {req.strategyId}" if req.strategyId else "firm-wide"
    compliance_store.append_audit(
        category="config", action="compliance.kill_switch",
        target=req.strategyId, decision="blocked" if req.on else None,
        summary=(f"Kill-switch {'ENGAGED' if req.on else 'released'} ({scope})"
                 + (f": {req.reason}" if req.reason else "")),
    )
    return _compliance_payload()


@api.post("/compliance/check")
def check_compliance(req: ComplianceSymbolInput):
    # ``symbol`` here is reused as the strategy name/id to pre-check.
    sel = (req.symbol or "").strip()
    if not sel:
        raise HTTPException(status_code=400, detail="strategy is required")
    return _compliance_payload(sel)


# NOTE: there is deliberately no endpoint to clear or edit the audit trail. The
# log is append-only by contract; ``compliance_store.clear_audit`` exists only for
# test setup and is never exposed over HTTP.


# ------------------------------ firm-wide audit log ---------------------------
@api.get("/audit")
def get_audit_log(
    user: str | None = None,
    category: str | None = None,
    action: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 200,
    _identity: auth.Identity = Depends(require_permission("compliance.config")),
):
    """Admin-only firm-wide audit trail with filters.

    Gated through the authoritative permission matrix (``compliance.config`` is
    admin-only) so it is server-enforced and consistent with the rest of the
    privileged surface. Scoped to the admin's firm via the request context (set
    in require_identity); ``user`` is an actor user id, ``category``/``action``
    exact matches, and ``since``/``until`` bound the ISO timestamp. Also returns
    the distinct actors and categories present so the viewer can populate its
    filter dropdowns.
    """
    from . import compliance_store
    entries = compliance_store.list_audit(
        limit=limit, category=category, actor_user_id=user,
        action=action, since=since, until=until,
    )
    return {
        "entries": entries,
        "actors": compliance_store.audit_actors(),
        "categories": compliance_store.audit_categories(),
    }


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


# ============================ firm admin console =============================
# Admin-only, firm-scoped self-service: manage team members & roles, firm risk
# limits & kill-switch, the firm profile, and a read-only billing view. Every
# route below is gated by ``require_role("admin")`` (server-authoritative — the
# UI hiding the console is convenience only) and every mutation is written to the
# firm's compliance audit trail (reusing ``compliance_store.append_audit`` with a
# benign ``decision="ok"``). All reads/writes are already firm-scoped because
# ``require_identity`` binds the tenant for the request.

ADMIN_ROLES = ("admin", "trader", "analyst", "read-only")


def _admin_audit(identity: auth.Identity, action: str, summary: str, detail: dict | None = None) -> None:
    """Record one admin-console action in the firm audit trail (best-effort)."""
    from . import compliance_store
    try:
        compliance_store.append_audit(
            action=action,
            decision="ok",
            summary=summary,
            detail={"actorId": identity.user_id, "actorEmail": identity.email, **(detail or {})},
            firm_id=identity.firm_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("admin audit failed (%s): %s", action, exc)


class AdminInviteInput(BaseModel):
    email: str
    name: str | None = None
    role: str | None = "trader"


class AdminRoleInput(BaseModel):
    role: str


class AdminActiveInput(BaseModel):
    active: bool


class AdminFirmInput(BaseModel):
    name: str


class AdminLimitsInput(BaseModel):
    limits: dict


class AdminKillSwitchInput(BaseModel):
    on: bool
    reason: str | None = None


class AcceptInviteInput(BaseModel):
    token: str
    name: str | None = None
    password: str


def _members_payload(identity: auth.Identity) -> dict:
    """The whole Team tab in one read: members, pending invites, billing/seats."""
    firm = auth_store.get_firm(identity.firm_id) or {"id": identity.firm_id, "name": "", "plan": "starter", "seats": 5}
    members = auth_store.list_users(identity.firm_id)
    invites = auth_store.list_invitations(identity.firm_id, status="pending")
    active_members = [m for m in members if m.get("active")]
    return {
        "firm": firm,
        "members": members,
        "invitations": invites,
        "roles": list(ADMIN_ROLES),
        "billing": {
            "plan": firm.get("plan", "starter"),
            "seats": firm.get("seats", 5),
            "seatsUsed": len(active_members),
            "seatsAvailable": max(0, int(firm.get("seats", 5)) - len(active_members)),
            "pendingInvites": len(invites),
        },
        "selfId": identity.user_id,
    }


@api.get("/admin/members")
def admin_list_members(identity: auth.Identity = Depends(require_role("admin"))):
    """List all firm members, pending invitations and the billing/seat view."""
    return _members_payload(identity)


@api.post("/admin/invitations")
def admin_create_invitation(
    req: AdminInviteInput,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Invite a teammate. Returns a one-time invite link the admin can share.

    The raw token is shown exactly once (only its hash is stored), so the link is
    the single way to accept. Re-inviting an email replaces the pending invite.
    """
    email = auth.normalize_email(req.email)
    name = (req.name or "").strip()
    role = auth.valid_role(req.role)
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if auth_store.email_exists(email):
        raise HTTPException(status_code=409, detail="A user with this email is already on your team")
    # Replace any existing pending invite for the same email so a fresh link is issued.
    existing = auth_store.get_pending_invitation_by_email(identity.firm_id, email)
    if existing:
        auth_store.revoke_invitation(existing["id"], identity.firm_id)
    token = auth.new_session_token()
    invite = auth_store.create_invitation(
        firm_id=identity.firm_id,
        email=email,
        name=name,
        role=role,
        token_hash=auth.hash_token(token),
    )
    _admin_audit(
        identity, "admin.invite",
        f"Invited {email} as {role}",
        {"inviteId": invite["id"], "email": email, "role": role},
    )
    return {"invitation": invite, "inviteToken": token, "members": _members_payload(identity)}


@api.delete("/admin/invitations/{invite_id}")
def admin_revoke_invitation(
    invite_id: str,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Revoke a pending invitation (firm-scoped)."""
    ok = auth_store.revoke_invitation(invite_id, identity.firm_id)
    if not ok:
        raise HTTPException(status_code=404, detail="No pending invitation with that id")
    _admin_audit(identity, "admin.invite.revoke", "Revoked an invitation", {"inviteId": invite_id})
    return _members_payload(identity)


def _require_member(identity: auth.Identity, user_id: str) -> dict:
    """Load a target user and assert it belongs to the admin's firm."""
    target = auth_store.get_user_by_id(user_id)
    if not target or target.get("firmId") != identity.firm_id:
        raise HTTPException(status_code=404, detail="No such member in your firm")
    return target


@api.post("/admin/users/{user_id}/role")
def admin_set_user_role(
    user_id: str,
    req: AdminRoleInput,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Change a member's role. Protects against demoting the last active admin."""
    target = _require_member(identity, user_id)
    new_role = auth.valid_role(req.role)
    # Guard: never leave a firm with zero active admins.
    if target["role"] == "admin" and new_role != "admin":
        if auth_store.count_active_admins(identity.firm_id) <= 1:
            raise HTTPException(status_code=400, detail="Your firm must keep at least one admin")
    updated = auth_store.update_user_role(user_id, new_role)
    _admin_audit(
        identity, "admin.user.role",
        f"Changed {target['email']} role {target['role']} → {new_role}",
        {"userId": user_id, "from": target["role"], "to": new_role},
    )
    return {"member": auth_store._user_public(updated) if updated else None, "members": _members_payload(identity)}


@api.post("/admin/users/{user_id}/active")
def admin_set_user_active(
    user_id: str,
    req: AdminActiveInput,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Activate or deactivate a member. Deactivation also revokes their sessions.

    Guards: an admin cannot deactivate themselves, and the firm's last active
    admin cannot be deactivated.
    """
    target = _require_member(identity, user_id)
    active = bool(req.active)
    if not active:
        if user_id == identity.user_id:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
        if target["role"] == "admin" and auth_store.count_active_admins(identity.firm_id) <= 1:
            raise HTTPException(status_code=400, detail="Your firm must keep at least one active admin")
    updated = auth_store.set_user_active(user_id, active)
    if not active:
        # Kick the user out immediately; require_identity also rejects them going forward.
        auth_store.delete_user_sessions(user_id)
    _admin_audit(
        identity, "admin.user.active",
        f"{'Reactivated' if active else 'Deactivated'} {target['email']}",
        {"userId": user_id, "active": active},
    )
    return {"member": auth_store._user_public(updated) if updated else None, "members": _members_payload(identity)}


@api.delete("/admin/users/{user_id}")
def admin_remove_user(
    user_id: str,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Permanently remove a member from the firm.

    Guards: an admin cannot remove themselves, and the last active admin cannot
    be removed.
    """
    target = _require_member(identity, user_id)
    if user_id == identity.user_id:
        raise HTTPException(status_code=400, detail="You cannot remove your own account")
    if target["role"] == "admin" and target.get("active") and auth_store.count_active_admins(identity.firm_id) <= 1:
        raise HTTPException(status_code=400, detail="Your firm must keep at least one active admin")
    auth_store.delete_user(user_id)
    _admin_audit(
        identity, "admin.user.remove",
        f"Removed {target['email']} from the firm",
        {"userId": user_id, "email": target["email"]},
    )
    return _members_payload(identity)


@api.post("/admin/firm")
def admin_update_firm(
    req: AdminFirmInput,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Edit the firm profile (currently the display name)."""
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Firm name is required")
    firm = auth_store.update_firm(identity.firm_id, name)
    _admin_audit(identity, "admin.firm.update", f"Renamed firm to “{name}”", {"name": name})
    return {"firm": firm}


@api.get("/admin/limits")
def admin_get_limits(identity: auth.Identity = Depends(require_role("admin"))):
    """Return the firm's risk limits + editor metadata and kill-switch state."""
    from . import compliance_store
    from .engine import compliance as comp
    cfg = compliance_store.get_config(identity.firm_id)
    return {
        "limits": cfg.get("limits", {}),
        "defs": comp.LIMIT_DEFS,
        "defaults": comp.DEFAULT_LIMITS,
        "killSwitch": bool(cfg.get("killSwitch")),
        "killReason": cfg.get("killReason"),
    }


@api.post("/admin/limits")
def admin_set_limits(
    req: AdminLimitsInput,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Update one or more firm-wide risk limits."""
    from . import compliance_store
    from .engine import compliance as comp
    cfg = compliance_store.set_limits(req.limits or {})
    _admin_audit(identity, "admin.limits.update", "Updated firm risk limits", {"limits": req.limits or {}})
    return {
        "limits": cfg.get("limits", {}),
        "defs": comp.LIMIT_DEFS,
        "defaults": comp.DEFAULT_LIMITS,
        "killSwitch": bool(cfg.get("killSwitch")),
        "killReason": cfg.get("killReason"),
    }


@api.post("/admin/kill-switch")
def admin_set_kill_switch(
    req: AdminKillSwitchInput,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Engage or release the firm-wide trading kill switch."""
    from . import compliance_store
    cfg = compliance_store.set_kill_switch(bool(req.on), reason=req.reason)
    _admin_audit(
        identity, "admin.kill_switch",
        f"Kill switch {'ENGAGED' if req.on else 'released'}",
        {"on": bool(req.on), "reason": req.reason},
    )
    return {"killSwitch": bool(cfg.get("killSwitch")), "killReason": cfg.get("killReason")}


@api.get("/admin/audit")
def admin_get_audit(
    limit: int = 50,
    identity: auth.Identity = Depends(require_role("admin")),
):
    """Return the firm's audit trail (admin actions + compliance gate decisions)."""
    from . import compliance_store
    return {"entries": compliance_store.list_audit(limit=limit, firm_id=identity.firm_id)}


# ---------------------- public: accept an invitation -------------------------
@public.get("/auth/invitation")
def auth_invitation_preview(token: str):
    """Preview a pending invitation by its raw token (for the accept screen).

    Returns the firm name, invited email and role so the joining user sees what
    they're accepting. Lapsed/used/revoked tokens read as invalid.
    """
    invite = auth_store.get_invitation_by_token_hash(auth.hash_token(token or ""))
    if not invite or invite.get("status") != "pending":
        raise HTTPException(status_code=404, detail="This invitation is no longer valid")
    expires = invite.get("expiresAt")
    if expires and str(expires) < auth_store._iso(auth_store._now()):
        raise HTTPException(status_code=410, detail="This invitation has expired")
    firm = auth_store.get_firm(invite["firmId"])
    return {
        "email": invite["email"],
        "name": invite.get("name"),
        "role": invite["role"],
        "firmName": firm["name"] if firm else "",
    }


@public.post(
    "/auth/accept-invite",
    response_model=models.AuthIdentity,
    dependencies=[Depends(security.rate_limit("auth", 10, 60))],
)
def auth_accept_invite(req: AcceptInviteInput, response: Response):
    """Accept an invitation: create the user in the inviting firm and sign them in."""
    invite = auth_store.get_invitation_by_token_hash(auth.hash_token(req.token or ""))
    if not invite or invite.get("status") != "pending":
        raise HTTPException(status_code=404, detail="This invitation is no longer valid")
    expires = invite.get("expiresAt")
    if expires and str(expires) < auth_store._iso(auth_store._now()):
        raise HTTPException(status_code=410, detail="This invitation has expired")
    password = req.password or ""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    email = invite["email"]
    if auth_store.email_exists(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    name = (req.name or invite.get("name") or "").strip() or email.split("@")[0]
    pw_hash, pw_salt = auth.hash_password(password)
    user = auth_store.create_user(
        firm_id=invite["firmId"],
        email=email,
        name=name,
        role=auth.valid_role(invite["role"]),
        password_hash=pw_hash,
        password_salt=pw_salt,
    )
    auth_store.accept_invitation(invite["id"])
    firm = auth_store.get_firm(invite["firmId"])
    token = auth.new_session_token()
    auth_store.create_session(auth.hash_token(token), user["id"], auth.SESSION_TTL_SECONDS)
    _set_session_cookie(response, token)
    _admin_audit_system(invite["firmId"], "admin.invite.accept", f"{email} joined as {user['role']}",
                        {"userId": user["id"], "email": email, "role": user["role"]})
    return {
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
        "firm": {"id": firm["id"], "name": firm["name"]} if firm else {"id": invite["firmId"], "name": ""},
        "permissions": permissions.allowed_actions(user["role"]),
    }


def _admin_audit_system(firm_id: str, action: str, summary: str, detail: dict | None = None) -> None:
    """Audit an action with no admin actor (e.g. a user self-accepting an invite)."""
    from . import compliance_store
    try:
        compliance_store.append_audit(
            action=action, decision="ok", summary=summary,
            detail=detail or {}, firm_id=firm_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("system audit failed (%s): %s", action, exc)


app.include_router(public)
app.include_router(api)
