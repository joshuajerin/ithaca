"""Money-path service logic, transport-agnostic — the SINGLE implementation of the writes.

The control-plane FastAPI app and the rest-gateway (the UI's only backend) both call these
functions over the SAME platform stores, so there is exactly one money-path implementation
regardless of which HTTP surface a human used. Each function:

- takes ``(platform, ctx, ...)`` where ``ctx`` carries ``tenant_id`` + actor identity,
- enforces the invariants (tenant scope; human-only money actions; declarative specs only),
- writes a trace event on every audited outcome (success, denial, error) — never ``except:
  pass``,
- raises :class:`ActionError(status, detail)` which each transport maps to its HTTP error.

State machine (paper): ``draft -> queued -> running -> promoted -> live -> paused -> retired``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from doomberg_platform import TransitionConflict
from pydantic import ValidationError as PydanticValidationError

from .deps import HUMAN_ACTOR_KINDS, Ctx
from .gate import evaluate_spec_gate
from .compliance_policy import effective_compliance_policy, effective_execution_control

__all__ = [
    "ActionError",
    "propose_strategy",
    "create_run",
    "cancel_run",
    "promote_run",
    "activate_run",
    "pause_run",
    "resume_run",
    "retire_run",
]


class ActionError(Exception):
    """A money-path action was refused. ``status`` is the HTTP status; ``detail`` the body."""

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


# ----------------------------------------------------------------------------------------
# Trace helper — every audited action writes an event with a server-assigned gap-free seq.
# ----------------------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(platform: Any, *, ctx: Ctx, run_id: str, event_type: str, data: dict[str, Any],
          origin_session_id: str | None = None) -> int:
    actor_kind = ctx.actor_kind if ctx.actor_kind in {"agent", "user", "system"} else "user"
    event = {
        "run_id": run_id,
        "seq": 0,  # store-assigned
        "ts": _now_iso(),
        "type": event_type,
        "tenant_id": ctx.tenant_id,
        "actor": {"kind": actor_kind, "id": ctx.actor_id},
        "data": data,
    }
    if origin_session_id is not None:
        event["origin_session_id"] = origin_session_id
    return platform.trace.append(event)


def _require_human(platform: Any, ctx: Ctx, run_id: str, action: str) -> None:
    """Agents may never take a money-path action. Audit + raise 403 if not human."""
    if ctx.actor_kind not in HUMAN_ACTOR_KINDS:
        _emit(platform, ctx=ctx, run_id=run_id, event_type="denial",
              data={"action": action, "reason": f"{action} requires a human actor",
                    "actor_kind": ctx.actor_kind})
        raise ActionError(403, f"{action} requires a human actor (X-Actor-Kind: human)")


def _require_scope(platform: Any, ctx: Ctx, run_id: str, action: str, scope: str) -> None:
    """Capability gate: the principal's credential must carry ``scope``.

    Independent of the human-actor rule — a credential may *request* (e.g. ``deploy:paper``)
    yet still be unable to *promote* because it is not a human actor. Audited denial + 403.
    """
    if not ctx.has_scope(scope):
        _emit(platform, ctx=ctx, run_id=run_id, event_type="denial",
              data={"action": action, "reason": f"missing required scope: {scope}",
                    "required_scope": scope, "scopes": sorted(ctx.scopes)})
        raise ActionError(403, f"{action} requires the {scope} scope")


# ----------------------------------------------------------------------------------------
# propose / create
# ----------------------------------------------------------------------------------------
def propose_strategy(platform: Any, ctx: Ctx, core: Any, spec: dict[str, Any]) -> dict[str, Any]:
    _require_scope(platform, ctx, str(uuid.uuid4()), "propose_strategy", "strategy:author")
    try:
        validated = core.validate_spec(spec)
    except PydanticValidationError as exc:
        denial_run_id = str(uuid.uuid4())
        _emit(platform, ctx=ctx, run_id=denial_run_id, event_type="denial",
              data={"action": "propose_strategy", "reason": "spec validation failed",
                    "errors": exc.errors(include_url=False)})
        raise ActionError(422, "spec validation failed") from exc

    created = platform.strategies.create(ctx.tenant_id, validated)
    origin = spec.get("origin_session_id") or validated.get("origin_session_id")
    proposal_run_id = str(uuid.uuid4())
    seq = _emit(platform, ctx=ctx, run_id=proposal_run_id, event_type="strategy_proposed",
                data={"strategy_id": created["id"], "version": created["version"],
                      "name": validated.get("name")},
                origin_session_id=str(origin) if origin else None)
    return {"id": created["id"], "version": created["version"], "state": "draft",
            "trace": {"run_id": proposal_run_id, "seq": seq}}


_CREATE_SCOPE = {"backtest": "deploy:backtest", "paper": "deploy:paper"}


def create_run(platform: Any, ctx: Ctx, *, strategy_id: str, kind: str,
               range_: str = "1y", idempotency_key: str | None = None) -> dict[str, Any]:
    # Authoring a backtest needs deploy:backtest; requesting a paper deployment needs
    # deploy:paper (which is "may REQUEST" — promotion still requires a human).
    required = _CREATE_SCOPE.get(kind)
    if required is not None:
        _require_scope(platform, ctx, str(uuid.uuid4()), f"create_run:{kind}", required)

    strategy = platform.strategies.get(ctx.tenant_id, strategy_id)
    if strategy is None:
        raise ActionError(404, "strategy not found")

    jobs = getattr(platform, "jobs", None)
    if idempotency_key and jobs is not None:
        existing = jobs.get_by_idempotency(ctx.tenant_id, idempotency_key)
        if existing is not None:
            existing_run = platform.runs.get(ctx.tenant_id, existing["run_id"])
            if existing_run is None:
                raise ActionError(409, "idempotency key points to missing run")
            return {"run_id": existing["run_id"], "state": existing_run["state"],
                    "kind": existing_run["kind"], "job_id": existing["job_id"],
                    "profile": existing["profile"], "idempotent": True}

    spec = dict(strategy["spec"])
    run_id = platform.runs.create(ctx.tenant_id, kind, strategy_id, spec)
    run = platform.runs.transition(ctx.tenant_id, run_id, "queued", expect=0)
    profile = "backtest" if kind == "backtest" else "interactive"
    job = None
    if jobs is not None:
        job = jobs.create_for_run(
            ctx.tenant_id,
            run_id,
            kind=kind,
            profile=profile,
            payload={"spec": spec, "range": range_, "strategy_id": strategy_id},
            idempotency_key=idempotency_key,
        )
        if job.get("run_id") != run_id:
            try:
                platform.runs.cancel(ctx.tenant_id, run_id, expect=run["version"])
            except Exception as exc:
                _emit(
                    platform,
                    ctx=ctx,
                    run_id=run_id,
                    event_type="error",
                    data={
                        "action": "create_run",
                        "reason": "duplicate idempotency cleanup failed",
                        "detail": str(exc),
                    },
                )
                raise ActionError(409, "duplicate idempotency cleanup failed") from exc
            existing_run = platform.runs.get(ctx.tenant_id, job["run_id"])
            if existing_run is None:
                raise ActionError(409, "idempotency key points to missing run")
            return {
                "run_id": job["run_id"],
                "state": existing_run["state"],
                "kind": existing_run["kind"],
                "job_id": job["job_id"],
                "profile": job["profile"],
                "idempotent": True,
            }
    origin = spec.get("origin_session_id") if isinstance(spec, dict) else None
    _emit(platform, ctx=ctx, run_id=run_id, event_type="run_transition",
          data={"from": "draft", "to": "queued", "kind": kind, "range": range_,
                "strategy_id": strategy_id, "job_id": job.get("job_id") if job else None,
                "profile": profile},
          origin_session_id=str(origin) if origin else None)
    return {"run_id": run_id, "state": run["state"], "kind": run["kind"],
            "job_id": job.get("job_id") if job else None, "profile": profile}


def cancel_run(platform: Any, ctx: Ctx, run_id: str, *, reason: str | None = None) -> dict[str, Any]:
    run = platform.runs.get(ctx.tenant_id, run_id)
    if run is None:
        raise ActionError(404, "run not found")
    _require_scope(platform, ctx, run_id, "cancel", "runs:cancel")
    if run["state"] in {"succeeded", "failed", "timeout", "cancelled", "promoted", "live",
                        "paused", "retired"}:
        raise ActionError(409, f"run in state {run['state']!r} cannot be cancelled")
    jobs = getattr(platform, "jobs", None)
    cancelled_jobs = jobs.cancel_by_run(ctx.tenant_id, run_id, reason=reason) if jobs else []
    try:
        updated = platform.runs.cancel(ctx.tenant_id, run_id, expect=run["version"])
    except TransitionConflict:
        latest = platform.runs.get(ctx.tenant_id, run_id)
        if latest is None:
            raise ActionError(404, "run not found")
        if latest["state"] in {"succeeded", "failed", "timeout", "cancelled", "promoted",
                               "live", "paused", "retired"}:
            raise ActionError(409, f"run in state {latest['state']!r} cannot be cancelled")
        try:
            updated = platform.runs.cancel(ctx.tenant_id, run_id, expect=latest["version"])
        except Exception as exc:
            _emit(platform, ctx=ctx, run_id=run_id, event_type="error",
                  data={"action": "cancel", "reason": "transition failed", "detail": str(exc)})
            raise ActionError(409, "cancel transition failed") from exc
    except Exception as exc:
        _emit(platform, ctx=ctx, run_id=run_id, event_type="error",
              data={"action": "cancel", "reason": "transition failed", "detail": str(exc)})
        raise ActionError(409, "cancel transition failed") from exc
    _emit(platform, ctx=ctx, run_id=run_id, event_type="run_transition",
          data={"from": run["state"], "to": "cancelled", "action": "cancel",
                "reason": reason, "cancelled_jobs": [j["job_id"] for j in cancelled_jobs]})
    return {"run_id": run_id, "state": updated["state"],
            "cancelled_jobs": [j["job_id"] for j in cancelled_jobs]}


# ----------------------------------------------------------------------------------------
# promote (queued/running/succeeded paper -> promoted) — human + gate
# ----------------------------------------------------------------------------------------
def promote_run(platform: Any, ctx: Ctx, run_id: str) -> dict[str, Any]:
    run = platform.runs.get(ctx.tenant_id, run_id)
    if run is None:
        raise ActionError(404, "run not found")

    # The money path needs BOTH: a human actor (no agent may self-promote) AND the
    # deploy:paper capability on the credential.
    _require_scope(platform, ctx, run_id, "promote", "deploy:paper")
    _require_human(platform, ctx, run_id, "promote")

    if run["kind"] != "paper":
        _emit(platform, ctx=ctx, run_id=run_id, event_type="denial",
              data={"action": "promote", "reason": "only paper runs may be promoted",
                    "kind": run["kind"]})
        raise ActionError(409, "only paper runs may be promoted")

    spec = run.get("spec")
    if not isinstance(spec, dict):
        _emit(platform, ctx=ctx, run_id=run_id, event_type="error",
              data={"action": "promote", "reason": "run has no spec to gate"})
        raise ActionError(409, "run has no spec to gate")

    compliance = effective_compliance_policy(platform, ctx.tenant_id)
    execution_control = effective_execution_control(platform, ctx.tenant_id)
    decision = evaluate_spec_gate(
        spec,
        restricted=compliance["restricted"],
        watch=compliance["watch"],
        firm_limits=compliance["limits"] if compliance["limits_enforced"] else None,
        kill_switch=execution_control["enabled"],
        kill_reason=execution_control["reason"],
    )
    if not compliance["available"]:
        decision.ok = False
        decision.violations.append("Compliance policy store is unavailable")
    if not decision.ok:
        _emit(platform, ctx=ctx, run_id=run_id, event_type="denial",
              data={"action": "promote", "reason": "compliance/risk gate blocked",
                    "gate": decision.to_dict()})
        raise ActionError(409, {"reason": "gate blocked", "gate": decision.to_dict()})

    try:
        state, version = run["state"], run["version"]
        if state == "queued":
            r = platform.runs.transition(ctx.tenant_id, run_id, "running", expect=version)
            state, version = r["state"], r["version"]
        if state in {"running", "succeeded"}:
            platform.runs.transition(ctx.tenant_id, run_id, "promoted", expect=version)
        else:
            raise ActionError(409, f"run in state {state!r} cannot be promoted")
    except ActionError:
        raise
    except Exception as exc:  # transition conflict / illegal transition — audit it.
        _emit(platform, ctx=ctx, run_id=run_id, event_type="error",
              data={"action": "promote", "reason": "transition failed", "detail": str(exc)})
        raise ActionError(409, "promote transition failed") from exc

    _emit(platform, ctx=ctx, run_id=run_id, event_type="run_transition",
          data={"to": "promoted", "gate": decision.to_dict()})
    return {"run_id": run_id, "state": "promoted", "gate": decision.to_dict()}


# ----------------------------------------------------------------------------------------
# paper deployment lifecycle (promoted <-> live <-> paused -> retired) — human actions
# ----------------------------------------------------------------------------------------
def _lifecycle(platform: Any, ctx: Ctx, run_id: str, *, action: str, to_state: str,
               allowed_from: set[str]) -> dict[str, Any]:
    run = platform.runs.get(ctx.tenant_id, run_id)
    if run is None:
        raise ActionError(404, "run not found")
    _require_scope(platform, ctx, run_id, action, "deploy:paper")
    _require_human(platform, ctx, run_id, action)
    if run["kind"] != "paper":
        raise ActionError(409, f"{action} applies only to paper deployments")
    if run["state"] not in allowed_from:
        _emit(platform, ctx=ctx, run_id=run_id, event_type="denial",
              data={"action": action, "reason": f"illegal from state {run['state']!r}",
                    "allowed_from": sorted(allowed_from)})
        raise ActionError(409, f"cannot {action} a run in state {run['state']!r}")
    try:
        r = platform.runs.transition(ctx.tenant_id, run_id, to_state, expect=run["version"])
    except Exception as exc:  # conflict / illegal — audit it.
        _emit(platform, ctx=ctx, run_id=run_id, event_type="error",
              data={"action": action, "reason": "transition failed", "detail": str(exc)})
        raise ActionError(409, f"{action} transition failed") from exc
    _emit(platform, ctx=ctx, run_id=run_id, event_type="run_transition",
          data={"from": run["state"], "to": to_state, "action": action})
    return {"run_id": run_id, "state": r["state"]}


def activate_run(platform: Any, ctx: Ctx, run_id: str) -> dict[str, Any]:
    """promoted -> live: start ticking the deployment (the scheduler picks it up)."""
    return _lifecycle(platform, ctx, run_id, action="activate", to_state="live",
                      allowed_from={"promoted", "paused"})


def pause_run(platform: Any, ctx: Ctx, run_id: str) -> dict[str, Any]:
    return _lifecycle(platform, ctx, run_id, action="pause", to_state="paused",
                      allowed_from={"live"})


def resume_run(platform: Any, ctx: Ctx, run_id: str) -> dict[str, Any]:
    return _lifecycle(platform, ctx, run_id, action="resume", to_state="live",
                      allowed_from={"paused"})


def retire_run(platform: Any, ctx: Ctx, run_id: str) -> dict[str, Any]:
    return _lifecycle(platform, ctx, run_id, action="retire", to_state="retired",
                      allowed_from={"promoted", "live", "paused"})
