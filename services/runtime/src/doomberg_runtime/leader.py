"""Runtime helpers for singleton active loops.

Queued work can scale horizontally through ``JobStore`` leases. Polling loops
such as trigger evaluation and paper scheduling need one active owner at a time
or they can duplicate firings/ticks. This helper gates a loop through the
platform ``LeaseStore`` when available and degrades to unguarded local execution
for tiny fake platforms used in tests.
"""

from __future__ import annotations

import os
import uuid
from typing import Any


def process_owner(prefix: str) -> str:
    host = os.environ.get("HOSTNAME") or "local"
    return f"{prefix}-{host}-{uuid.uuid4().hex[:10]}"


def acquire_loop_lease(
    platform: Any,
    *,
    lease_name: str,
    owner_id: str,
    ttl_seconds: float,
    role: str,
) -> bool:
    leases = getattr(platform, "leases", None)
    if leases is None:
        return True
    lease = leases.acquire(
        lease_name,
        owner_id,
        ttl_seconds=ttl_seconds,
        metadata={"role": role, "pid": os.getpid(), "host": os.environ.get("HOSTNAME")},
    )
    return lease is not None


def release_loop_lease(platform: Any, *, lease_name: str, owner_id: str) -> None:
    leases = getattr(platform, "leases", None)
    if leases is not None:
        leases.release(lease_name, owner_id)
