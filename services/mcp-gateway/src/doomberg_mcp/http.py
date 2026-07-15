"""Standards-based dual-auth HTTP transport for the Ithaca MCP server.

Interactive clients authenticate through Clerk OAuth; automation clients retain Clerk and
legacy API-key support.  Authentication is delegated to the MCP SDK so protected-resource
metadata and Bearer challenges remain protocol-correct.
"""
from __future__ import annotations

import os
from typing import Any

import anyio
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings

from doomberg_platform import (
    ClerkApiError,
    ClerkApiUnavailable,
    ClerkAuthConfigurationError,
    ClerkIdentityService,
    ClerkIdentityUnavailable,
    ClerkTokenInvalid,
    Platform,
    build_agent_key_store,
    open_db,
)

MCP_RESOURCE_URL_ENV = "ITHACA_MCP_RESOURCE_URL"
DEFAULT_MCP_RESOURCE_URL = "https://mcp.tradeithaca.com/mcp"
MCP_OAUTH_SCOPE_ENV = "ITHACA_MCP_OAUTH_SCOPE"
DEFAULT_MCP_OAUTH_SCOPE = "ithaca:agent"

# OAuth is intentionally read-oriented. It never inherits privileged deployment, execution,
# credential-administration, approval-decision, or trigger-write capabilities.
SAFE_OAUTH_SCOPES = frozenset({
    "agent:read", "data:read", "artifacts:read", "approvals:read",
    "triggers:read", "alerts:read", "runs:write", "runs:cancel",
})


def resource_url() -> str:
    return (os.environ.get(MCP_RESOURCE_URL_ENV) or DEFAULT_MCP_RESOURCE_URL).strip()


def oauth_scope() -> str:
    return (os.environ.get(MCP_OAUTH_SCOPE_ENV) or DEFAULT_MCP_OAUTH_SCOPE).strip()


def looks_like_agent_api_key(token: str) -> bool:
    return token.startswith(("ak_", "dmbg_", "ith_"))


class CompositeTokenVerifier(TokenVerifier):
    """Accept Clerk OAuth access tokens and existing scoped API keys as Bearer tokens."""

    def __init__(self, *, agent_keys: Any, identity: ClerkIdentityService) -> None:
        self._agent_keys = agent_keys
        self._identity = identity

    async def verify_token(self, token: str) -> AccessToken | None:
        if looks_like_agent_api_key(token):
            return await self._verify_api_key(token)
        return await self._verify_oauth_token(token)

    async def _verify_api_key(self, token: str) -> AccessToken | None:
        try:
            info = await anyio.to_thread.run_sync(self._agent_keys.verify, token)
        except (ClerkApiUnavailable, ClerkApiError):
            # Fail closed.  The SDK will issue the normal 401 challenge without leaking the
            # operational detail or credential value.
            return None
        if not info or not info.get("tenant_id"):
            return None
        principal_scopes = [str(scope) for scope in (info.get("scopes") or [])]
        # SDK gateway admission has one coarse required scope.  Preserve API-key capability
        # scopes separately and add only the admission marker to the SDK-facing token.
        scopes = sorted(set(principal_scopes) | {oauth_scope()})
        key_id = str(info.get("key_id") or "") or None
        return AccessToken(
            token="<api-key>", client_id=key_id or "api-key", subject=key_id,
            scopes=scopes, resource=resource_url(),
            claims={
                "credential_kind": "api_key", "tenant_id": str(info["tenant_id"]),
                "principal_scopes": principal_scopes, "key_id": key_id,
            },
        )

    async def _verify_oauth_token(self, token: str) -> AccessToken | None:
        try:
            identity = await anyio.to_thread.run_sync(
                lambda: self._identity.verify_oauth_token(
                    token, audience=resource_url(), required_scopes=[oauth_scope()]
                )
            )
            principal = await anyio.to_thread.run_sync(self._identity.resolve_user_and_tenant, identity)
        except (ClerkTokenInvalid, ClerkAuthConfigurationError, ClerkIdentityUnavailable):
            return None
        scopes = sorted(SAFE_OAUTH_SCOPES)
        return AccessToken(
            token="<oauth>", client_id=identity.client_id or "clerk-oauth",
            subject=identity.subject, scopes=sorted(identity.scopes),
            expires_at=identity.expires_at, resource=resource_url(),
            claims={
                "credential_kind": "oauth", "tenant_id": principal.tenant_id,
                "principal_scopes": scopes, "clerk_subject": identity.subject,
            },
        )


def _auth_settings(identity: ClerkIdentityService) -> AuthSettings:
    identity.validate_configuration(require_issuer=True)
    resource = resource_url()
    if not resource.startswith("https://"):
        raise ClerkAuthConfigurationError(f"{MCP_RESOURCE_URL_ENV} must be canonical HTTPS")
    return AuthSettings(
        issuer_url=identity.issuer,  # validated above
        resource_server_url=resource,
        required_scopes=[oauth_scope()],
        service_documentation_url=os.environ.get(
            "ITHACA_MCP_SERVICE_DOCUMENTATION_URL", "https://app.tradeithaca.com/settings"
        ),
    )


def build_http_app(toolset=None, verifier: Any | None = None, *, host: str | None = None,
                   port: int | None = None):
    """Build an SDK-authenticated Streamable HTTP app.

    ``verifier`` remains injectable for compatibility tests.  Production builds a shared
    Clerk identity service and refuses startup when OAuth verification cannot be configured.
    """
    from .server import create_server

    db = open_db(os.environ.get("DOOMBERG_DB", ":memory:"))
    platform = Platform(db)
    identity = ClerkIdentityService.from_environment(db=db, users=platform.users, auth=platform.auth)
    token_verifier: TokenVerifier
    if verifier is None:
        token_verifier = CompositeTokenVerifier(agent_keys=build_agent_key_store(db), identity=identity)
    elif hasattr(verifier, "verify_token"):
        token_verifier = verifier
    else:
        # The old injectable AuthStore shape is useful in local tests; wrap it without
        # changing production's SDK authentication path.
        token_verifier = CompositeTokenVerifier(agent_keys=verifier, identity=identity)
    mcp, ts = create_server(
        toolset, http=True, token_verifier=token_verifier, auth_settings=_auth_settings(identity)
    )
    if host is not None:
        mcp.settings.host = host
    if port is not None:
        mcp.settings.port = port
    return mcp.streamable_http_app(), mcp, ts


def serve_http(toolset=None, verifier=None, host: str = "0.0.0.0", port: int = 8080) -> None:
    import uvicorn

    app, _mcp, _ts = build_http_app(toolset, verifier, host=host, port=port)
    uvicorn.run(app, host=host, port=port, log_level="info")
