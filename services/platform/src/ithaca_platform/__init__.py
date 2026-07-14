"""ithaca-platform — platform system-of-record stores.

Trace events (append-only, gap-free seq per run), runs (state machine with optimistic
version guard), strategies (immutable versioned specs), jobs, auth, and governance rows.
Local/dev can use SQLite; production can use Postgres by passing a Postgres DSN as
``ITHACA_DB``.
``tenant_id`` is a hard isolation invariant: it is the first argument and a column on
every table, and every query filters by it.

See ``docs/plans/ithaca-v2/INTERFACES.md`` for the seam this package conforms to.
"""

from __future__ import annotations

from .adaptive_dashboard_store import (
    ADAPTIVE_WIDGET_IDS,
    DEFAULT_ADAPTIVE_DASHBOARD_SPEC,
    AdaptiveDashboardProfileStore,
    AdaptiveDashboardSpecError,
    validate_adaptive_dashboard_spec,
)
from .auth_store import VALID_SCOPES, AuthStore, hash_secret, is_agent_key, key_prefixes
from .book_store import BookConflict, BookNotFound, BookStore
from .clerk_api_keys import (
    AgentKeyStore,
    ClerkApiError,
    ClerkApiUnavailable,
    ClerkManagedApiKeyStore,
    ClerkWaitlistService,
    build_agent_key_store,
)
from .control_store import (
    ApprovalStore,
    ArtifactStore,
    CompliancePolicyConflict,
    CompliancePolicyStore,
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
from .feedback_store import FeedbackStore
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
from .worker_store import WorkerHeartbeatStore

__all__ = [
    "open_db",
    "Db",
    "FeedbackStore",
    "Platform",
    "TraceStore",
    "RunStore",
    "StrategyStore",
    "BookStore",
    "AuthStore",
    "is_agent_key",
    "key_prefixes",
    "AgentKeyStore",
    "ClerkApiError",
    "ClerkApiUnavailable",
    "ClerkManagedApiKeyStore",
    "ClerkWaitlistService",
    "build_agent_key_store",
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
    "CompliancePolicyStore",
    "CompliancePolicyConflict",
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
    "WorkerHeartbeatStore",
]
