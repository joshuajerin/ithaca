"""doomberg-platform — platform system-of-record stores.

Trace events (append-only, gap-free seq per run), runs (state machine with optimistic
version guard), strategies (immutable versioned specs), jobs, auth, and governance rows.
Local/dev can use SQLite; production can use Postgres by passing a Postgres DSN as
``DOOMBERG_DB``.
``tenant_id`` is a hard isolation invariant: it is the first argument and a column on
every table, and every query filters by it.

See ``docs/plans/doomberg-v2/INTERFACES.md`` for the seam this package conforms to.
"""

from __future__ import annotations

from .adaptive_dashboard_store import (
    ADAPTIVE_WIDGET_IDS,
    DEFAULT_ADAPTIVE_DASHBOARD_SPEC,
    AdaptiveDashboardProfileStore,
    AdaptiveDashboardSpecError,
    validate_adaptive_dashboard_spec,
)
from .auth_store import VALID_SCOPES, AuthStore, hash_secret
from .book_store import BookConflict, BookNotFound, BookStore
from .control_store import (
    ApprovalStore,
    ArtifactStore,
    DeliveryTargetStore,
    ExecutionControlConflict,
    ExecutionControlStore,
    ExecutionStore,
    NotificationStore,
    ProviderStore,
    TriggerBaselineStore,
    TriggerStore,
)
from .db import Db, open_db
from .job_store import JobConflict, JobNotFound, JobStore
from .job_profiles import (
    JOB_PROFILES,
    JobProfile,
    UnknownJobProfile,
    admission_metadata,
    all_job_profile_manifests,
    get_job_profile,
    job_profile_manifest,
)
from .lease_store import LeaseConflict, LeaseStore
from .platform import Platform
from .run_store import (
    RunNotFound,
    RunStore,
    TransitionConflict,
    TransitionError,
)
from .strategy_store import StrategyStore
from .trace_store import TraceStore
from .user_store import SessionError, UserStore

__all__ = [
    "open_db",
    "Db",
    "Platform",
    "TraceStore",
    "RunStore",
    "StrategyStore",
    "BookStore",
    "AuthStore",
    "AdaptiveDashboardProfileStore",
    "ADAPTIVE_WIDGET_IDS",
    "DEFAULT_ADAPTIVE_DASHBOARD_SPEC",
    "AdaptiveDashboardSpecError",
    "validate_adaptive_dashboard_spec",
    "JobStore",
    "JOB_PROFILES",
    "JobProfile",
    "UnknownJobProfile",
    "admission_metadata",
    "all_job_profile_manifests",
    "get_job_profile",
    "job_profile_manifest",
    "LeaseStore",
    "ArtifactStore",
    "ApprovalStore",
    "ProviderStore",
    "ExecutionStore",
    "ExecutionControlStore",
    "ExecutionControlConflict",
    "TriggerStore",
    "TriggerBaselineStore",
    "NotificationStore",
    "DeliveryTargetStore",
    "VALID_SCOPES",
    "hash_secret",
    "TransitionError",
    "TransitionConflict",
    "RunNotFound",
    "JobConflict",
    "JobNotFound",
    "LeaseConflict",
    "BookConflict",
    "BookNotFound",
    "UserStore",
    "SessionError",
]
