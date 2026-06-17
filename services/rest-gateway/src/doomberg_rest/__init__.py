"""doomberg-rest-gateway — REST + SSE gateway feeding the web UI from the platform stores.

The web UI's ONLY backend (the browser never speaks MCP). Read-only over the platform
system-of-record; tenant-scoped on every path via the ``X-Tenant-Id`` header.

See ``docs/plans/doomberg-v2/INTERFACES.md`` for the ``doomberg_rest`` seam.
"""

from __future__ import annotations

from .app import Stores, create_app
from .readmodel import shape_run, shape_run_row
from .sse import event_stream, format_event, keepalive_comment, parse_last_event_id

__all__ = [
    "create_app",
    "Stores",
    "shape_run",
    "shape_run_row",
    "event_stream",
    "format_event",
    "keepalive_comment",
    "parse_last_event_id",
]
