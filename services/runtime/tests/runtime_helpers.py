from __future__ import annotations

import uuid
from typing import Any


def seed_queued_run(platform: Any, tenant_id: str, spec: dict, kind: str = "backtest") -> str:
    run_id = platform.runs.create(tenant_id, kind, str(uuid.uuid4()), spec)
    platform.runs.transition(tenant_id, run_id, "queued", expect=0)
    return run_id
