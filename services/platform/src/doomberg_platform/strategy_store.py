"""Immutable, versioned strategy spec store, tenant-scoped.

``create`` mints a new row every time and returns ``{"id", "version"}``. Proposing a spec
whose ``name`` already exists for the tenant produces a NEW version of that named strategy
(versions are monotonic per name). Rows are never mutated in place — each accepted edit is
a fresh immutable version, preserving the audit trail.

The control plane is expected to validate the spec via ``core.validate_spec`` (which clears
server-stamped ``id``/``version``/``tenant_id``) before persisting. This store stamps the
authoritative ``id``, ``version``, and ``tenant_id`` into the stored copy.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: Any) -> dict[str, Any]:
    spec = json.loads(row["spec"])
    return {
        "id": row["strategy_id"],
        "tenant_id": row["tenant_id"],
        "name": row["name"],
        "version": row["version"],
        "spec": spec,
        "created_at": row["created_at"],
    }


class StrategyStore:
    """Immutable versioned strategy specs (same name -> new version)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def create(self, tenant_id: str, spec: dict[str, Any]) -> dict[str, Any]:
        """Persist a new immutable strategy version; returns ``{"id", "version"}``.

        ``spec["name"]`` is required. If a strategy with that name already exists for the
        tenant, the new row reuses that strategy's id and bumps its version; otherwise a
        fresh id is minted at version 1. The server stamps ``id``/``version``/``tenant_id``
        into the stored spec copy.
        """
        tenant_id = str(tenant_id)
        name = spec.get("name")
        if not name:
            raise ValueError("strategy spec requires a non-empty 'name'")

        with self._db.write_lock:
            with self._db.conn as conn:
                # Find an existing strategy with this name (latest version) to extend.
                existing = conn.execute(
                    "SELECT strategy_id, MAX(version) AS v FROM strategies "
                    "WHERE tenant_id = ? AND name = ?",
                    (tenant_id, name),
                ).fetchone()

                if existing and existing["strategy_id"] is not None:
                    strategy_id = existing["strategy_id"]
                    version = int(existing["v"]) + 1
                else:
                    strategy_id = str(uuid.uuid4())
                    version = 1

                stamped = dict(spec)
                stamped["id"] = strategy_id
                stamped["version"] = version
                stamped["tenant_id"] = tenant_id

                conn.execute(
                    "INSERT INTO strategies "
                    "(tenant_id, strategy_id, name, version, spec, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        tenant_id,
                        strategy_id,
                        name,
                        version,
                        json.dumps(stamped),
                        _now(),
                    ),
                )

        return {"id": strategy_id, "version": version}

    def get(self, tenant_id: str, strategy_id: str) -> dict[str, Any] | None:
        """Return the LATEST version of a strategy by id, tenant-scoped."""
        tenant_id = str(tenant_id)
        strategy_id = str(strategy_id)
        row = self._db.conn.execute(
            "SELECT * FROM strategies "
            "WHERE tenant_id = ? AND strategy_id = ? "
            "ORDER BY version DESC LIMIT 1",
            (tenant_id, strategy_id),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def get_version(
        self, tenant_id: str, strategy_id: str, version: int
    ) -> dict[str, Any] | None:
        """Return a specific immutable version of a strategy, tenant-scoped."""
        tenant_id = str(tenant_id)
        strategy_id = str(strategy_id)
        row = self._db.conn.execute(
            "SELECT * FROM strategies "
            "WHERE tenant_id = ? AND strategy_id = ? AND version = ?",
            (tenant_id, strategy_id, int(version)),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        """List the LATEST version of each strategy for the tenant."""
        tenant_id = str(tenant_id)
        rows = self._db.conn.execute(
            "SELECT s.* FROM strategies s "
            "JOIN (SELECT strategy_id, MAX(version) AS v FROM strategies "
            "      WHERE tenant_id = ? GROUP BY strategy_id) latest "
            "  ON s.strategy_id = latest.strategy_id AND s.version = latest.v "
            "WHERE s.tenant_id = ? "
            "ORDER BY s.created_at ASC, s.strategy_id ASC",
            (tenant_id, tenant_id),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
