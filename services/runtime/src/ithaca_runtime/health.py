"""Small fail-soft reporter for durable worker process heartbeats."""

from __future__ import annotations

import os
from typing import Any


class WorkerReporter:
    def __init__(
        self,
        platform: Any,
        *,
        worker_id: str,
        role: str,
        ttl_seconds: float,
    ) -> None:
        self.store = getattr(platform, "worker_heartbeats", None)
        self.worker_id = str(worker_id)
        self.role = str(role)
        self.ttl_seconds = max(5.0, float(ttl_seconds))

    def pulse(
        self,
        *,
        status: str = "healthy",
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.store is None:
            return
        payload = {"pid": os.getpid(), "host": os.environ.get("HOSTNAME")}
        payload.update(metadata or {})
        self.store.heartbeat(
            self.worker_id,
            self.role,
            ttl_seconds=self.ttl_seconds,
            status=status,
            detail=detail,
            metadata=payload,
        )

    def stop(self, detail: str = "worker loop stopped") -> None:
        if self.store is not None:
            self.store.stop(self.worker_id, self.role, detail=detail)
