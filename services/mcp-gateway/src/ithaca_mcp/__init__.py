"""ithaca-mcp-gateway — the primary product surface (MCP tools the BYO agent calls)."""
from .authorization import Principal, RESOURCE_SCOPES, TOOL_SCOPES
from .http import CompositeTokenVerifier, build_http_app, serve_http
from .server import Toolset, create_server
from .trace import InMemoryTrace, PlatformTraceSink, Tracer

__all__ = [
    "Toolset",
    "create_server",
    "InMemoryTrace",
    "PlatformTraceSink",
    "Tracer",
    "Principal",
    "CompositeTokenVerifier",
    "TOOL_SCOPES",
    "RESOURCE_SCOPES",
    "build_http_app",
    "serve_http",
]
