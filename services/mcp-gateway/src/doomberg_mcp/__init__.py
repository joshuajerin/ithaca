"""doomberg-mcp-gateway — the primary product surface (MCP tools the BYO agent calls)."""
from .http import (
    Principal,
    TenantAuthMiddleware,
    build_auth_store,
    build_http_app,
    current_principal,
    serve_http,
)
from .server import Toolset, create_server
from .trace import InMemoryTrace, PlatformTraceSink, Tracer

__all__ = [
    "Toolset",
    "create_server",
    "InMemoryTrace",
    "PlatformTraceSink",
    "Tracer",
    "Principal",
    "TenantAuthMiddleware",
    "build_auth_store",
    "build_http_app",
    "current_principal",
    "serve_http",
]
