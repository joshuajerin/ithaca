"""Tenant-scoped product feedback persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class FeedbackStore:
    def __init__(self, db: Any) -> None:
        self._db = db

    def create(self, tenant_id: str, user_id: str, message: str) -> dict[str, str]:
        feedback_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self._db.write_lock:
            with self._db.conn as conn:
                conn.execute(
                    "INSERT INTO feedback "
                    "(feedback_id, tenant_id, user_id, message, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (feedback_id, str(tenant_id), str(user_id), message, created_at),
                )
        return {"feedback_id": feedback_id, "created_at": created_at}
