"""Typed public contracts for dashboard read-model endpoints."""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DashboardStatus = Literal["ready", "empty", "stale", "unavailable"]
Scalar = str | int | float | bool
DataT = TypeVar("DataT")


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DashboardError(PublicModel):
    code: str
    message: str


class DashboardEnvelope(PublicModel, Generic[DataT]):
    status: DashboardStatus
    as_of: str | None
    source: str
    entitlement_class: str | None
    freshness_ms: int | None
    data: DataT
    error: DashboardError | None


class RunView(PublicModel):
    run_id: str | None
    kind: str | None
    state: str | None
    strategy_id: str | None
    created_at: str | None
    updated_at: str | None


class EquityPoint(PublicModel):
    d: str
    v: int | float


class BacktestView(RunView):
    equity_curve: list[EquityPoint]
    stats: dict[str, int | float]


class BookView(PublicModel):
    run_id: str | None
    capital: int | float | None
    gross: int | float | None
    cash: int | float | None
    weights: dict[str, int | float]
    updated_at: str | None


class PaperRunView(RunView):
    book: BookView | None


class RunCounts(PublicModel):
    total: int
    active: int
    by_state: dict[str, int]


class DashboardSummaryData(PublicModel):
    run_counts: RunCounts
    latest_run: RunView | None
    latest_backtest: BacktestView | None
    latest_paper: PaperRunView | None


class RiskBacktest(PublicModel):
    run_id: str | None
    metrics: dict[str, int | float]


class DashboardRiskData(PublicModel):
    backtest: RiskBacktest | None
    paper_exposure: BookView | None


class TriggerView(PublicModel):
    trigger_id: str | None
    name: str | None
    state: str | None
    created_at: str | None
    updated_at: str | None


class AlertView(PublicModel):
    notification_id: str | None
    event_type: str | None
    subject_type: str | None
    subject_id: str | None
    priority: str | None
    state: str | None
    payload: dict[str, Scalar]
    created_at: str | None
    updated_at: str | None


class DashboardActivityData(PublicModel):
    runs: list[RunView]
    triggers: list[TriggerView]
    alerts: list[AlertView]


class EntitlementView(PublicModel):
    dataset: str | None = None
    entitlement_class: str | None = None
    permitted_use: list[str] = Field(default_factory=list)
    freshness_class: str | None = None
    as_of: str | None = None


class ProviderConnectionView(PublicModel):
    connection_id: str | None
    provider: str
    state: str | None
    capabilities: list[str]
    entitlements: list[EntitlementView]
    credential_configured: bool
    created_at: str | None
    updated_at: str | None


class ProviderCounts(PublicModel):
    total: int
    connected: int


class ProviderStatusData(PublicModel):
    connections: list[ProviderConnectionView]
    counts: ProviderCounts
    live_engine_configured: bool


class SnapshotView(PublicModel):
    snapshot_id: str | None
    provider: str
    dataset: str | None
    entitlement_class: str | None
    as_of: str | None
    created_at: str | None


class DashboardMarketData(PublicModel):
    snapshots: list[SnapshotView]
    quote_providers: list[ProviderConnectionView]
