"""Hosted MCP authentication is delegated to the SDK TokenVerifier/AuthSettings path."""
from __future__ import annotations

import pytest

from ithaca_mcp.http import CompositeTokenVerifier, looks_like_agent_api_key
from ithaca_mcp import create_server
from ithaca_mcp.authorization import RESOURCE_SCOPES, TOOL_SCOPES


class _Keys:
    def verify(self, token: str):
        if token == "dmbg_test_key":
            return {"tenant_id": "tenant-a", "key_id": "key-a", "scopes": ["data:read"]}
        return None


class _Identity:
    def verify_oauth_token(self, token: str, *, audience: str, required_scopes: list[str]):
        if token != "oauth-token":
            from ithaca_platform import ClerkTokenInvalid
            raise ClerkTokenInvalid("invalid")
        from ithaca_platform import VerifiedClerkIdentity
        return VerifiedClerkIdentity("user_a", "oauth", "client_a", frozenset(required_scopes), 1234, {})

    def resolve_user_and_tenant(self, identity):
        from ithaca_platform import ResolvedClerkPrincipal
        return ResolvedClerkPrincipal("user-a", "tenant-a", identity.subject, {})


@pytest.mark.asyncio
async def test_composite_verifier_preserves_api_key_scopes() -> None:
    verifier = CompositeTokenVerifier(agent_keys=_Keys(), identity=_Identity())
    result = await verifier.verify_token("dmbg_test_key")
    assert result is not None
    assert result.claims["credential_kind"] == "api_key"
    assert result.claims["tenant_id"] == "tenant-a"
    assert result.claims["principal_scopes"] == ["data:read"]
    # Gateway admission scope is not confused with the key's capabilities.
    assert "openid" in result.scopes


@pytest.mark.asyncio
async def test_composite_verifier_builds_safe_oauth_principal() -> None:
    verifier = CompositeTokenVerifier(agent_keys=_Keys(), identity=_Identity())
    result = await verifier.verify_token("oauth-token")
    assert result is not None
    assert result.claims["credential_kind"] == "oauth"
    assert result.claims["tenant_id"] == "tenant-a"
    assert "deploy:live" not in result.claims["principal_scopes"]
    assert "approvals:decide" not in result.claims["principal_scopes"]


def test_existing_and_legacy_api_key_prefixes_are_recognized() -> None:
    assert looks_like_agent_api_key("ak_x")
    assert looks_like_agent_api_key("dmbg_x")
    assert looks_like_agent_api_key("ith_x")
    assert not looks_like_agent_api_key("eyJhbGciOiJSUzI1NiJ9")


@pytest.mark.asyncio
async def test_every_registered_mcp_surface_has_explicit_authorization_policy() -> None:
    mcp, _ = create_server()
    assert {tool.name for tool in await mcp.list_tools()} == set(TOOL_SCOPES)
    resources = {str(resource.uri) for resource in await mcp.list_resources()}
    templates = {template.uriTemplate for template in await mcp.list_resource_templates()}
    assert resources | templates == set(RESOURCE_SCOPES)
