"""Clerk-managed API keys for Doomberg's agent and MCP authentication.

Clerk owns secret generation, storage, verification, metadata, and revocation. Doomberg
only adds its tenant claim and enforces the existing capability scopes. Legacy ``dmbg_``
keys remain verifiable during migration, but new keys are created in Clerk whenever
``CLERK_SECRET_KEY`` is configured.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from .auth_store import VALID_SCOPES, AuthStore
from .db import Db

__all__ = [
    "AgentKeyStore",
    "ClerkApiError",
    "ClerkApiUnavailable",
    "ClerkManagedApiKeyStore",
    "build_agent_key_store",
]

_MANAGED_CLAIM = "doomberg_managed"
_TENANT_CLAIM = "doomberg_tenant_id"


class ClerkApiError(RuntimeError):
    """Clerk rejected a managed API-key operation."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ClerkApiUnavailable(ClerkApiError):
    """Clerk could not be reached or returned a server-side failure."""


def _validate_scopes(scopes: list[str]) -> list[str]:
    values = list(dict.fromkeys(str(scope) for scope in (scopes or [])))
    invalid = [scope for scope in values if scope not in VALID_SCOPES]
    if invalid:
        raise ValueError(
            f"unissuable scope(s): {invalid} (valid: {sorted(VALID_SCOPES)})"
        )
    return values


def _iso_from_milliseconds(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


class ClerkManagedApiKeyStore:
    """Small Backend API client with Doomberg-specific ownership checks."""

    def __init__(
        self,
        db: Db,
        secret_key: str,
        *,
        api_url: str = "https://api.clerk.com/v1",
        api_version: str = "2026-05-12",
        timeout_s: float = 5.0,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        if not secret_key.strip():
            raise ValueError("Clerk secret key must be non-empty")
        self._db = db
        self._secret_key = secret_key.strip()
        self._api_url = api_url.rstrip("/")
        self._api_version = api_version.strip()
        self._timeout_s = timeout_s
        self._urlopen = urlopen or urllib.request.urlopen

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._api_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._secret_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Doomberg/1.0 (Clerk managed API keys)",
        }
        if self._api_version:
            headers["Clerk-API-Version"] = self._api_version
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with self._urlopen(request, timeout=self._timeout_s) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            detail = self._error_detail(raw) or f"Clerk API returned HTTP {exc.code}"
            if exc.code >= 500:
                raise ClerkApiUnavailable(detail, status_code=exc.code) from exc
            raise ClerkApiError(detail, status_code=exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ClerkApiUnavailable("Clerk API is unavailable") from exc
        try:
            value = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            raise ClerkApiUnavailable("Clerk API returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise ClerkApiUnavailable("Clerk API returned an invalid response")
        return value

    @staticmethod
    def _error_detail(raw: bytes) -> str | None:
        try:
            payload = json.loads(raw or b"{}")
            errors = payload.get("errors") or []
            if errors and isinstance(errors[0], dict):
                return str(errors[0].get("long_message") or errors[0].get("message") or "")
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        return None

    def create_key(
        self,
        *,
        subject: str,
        tenant_id: str,
        scopes: list[str],
        name: str = "Doomberg agent key",
    ) -> tuple[str, str]:
        self._require_subject_tenant(subject, tenant_id)
        scope_list = _validate_scopes(scopes)
        result = self._request(
            "POST",
            "/api_keys",
            body={
                "name": name,
                "description": "Doomberg MCP and agent access",
                "subject": subject,
                "created_by": subject,
                "scopes": scope_list,
                "claims": {_MANAGED_CLAIM: True, _TENANT_CLAIM: tenant_id},
            },
        )
        secret = str(result.get("secret") or "")
        key_id = str(result.get("id") or "")
        if not secret or not key_id:
            raise ClerkApiUnavailable("Clerk did not return the new API key secret")
        return secret, key_id

    def verify(self, secret: str) -> dict[str, Any] | None:
        if not isinstance(secret, str) or not secret.startswith("ak_"):
            return None
        try:
            result = self._request("POST", "/api_keys/verify", body={"secret": secret})
        except ClerkApiError as exc:
            if not isinstance(exc, ClerkApiUnavailable) and exc.status_code in {400, 401, 404}:
                return None
            raise
        principal = self._principal(result)
        if principal is None:
            return None
        subject = str(result.get("subject") or "")
        if not self._subject_belongs_to_tenant(subject, principal["tenant_id"]):
            return None
        return principal

    def list_keys(self, *, subject: str, tenant_id: str) -> list[dict[str, Any]]:
        self._require_subject_tenant(subject, tenant_id)
        offset = 0
        items: list[dict[str, Any]] = []
        while True:
            page = self._request(
                "GET",
                "/api_keys",
                query={
                    "subject": subject,
                    "include_invalid": "true",
                    "limit": 100,
                    "offset": offset,
                },
            )
            data = page.get("data") or []
            if not isinstance(data, list):
                raise ClerkApiUnavailable("Clerk returned an invalid API key list")
            for item in data:
                if isinstance(item, dict) and self._is_managed_for_tenant(item, tenant_id):
                    items.append(self._metadata(item))
            offset += len(data)
            total = int(page.get("total_count") or 0)
            if not data or offset >= total:
                break
        return items

    def revoke_key(self, *, key_id: str, subject: str, tenant_id: str) -> bool:
        owned = {item["key_id"] for item in self.list_keys(subject=subject, tenant_id=tenant_id)}
        if key_id not in owned:
            return False
        self._request(
            "POST",
            f"/api_keys/{urllib.parse.quote(key_id, safe='')}/revoke",
            body={"revocation_reason": "Revoked by Doomberg user"},
        )
        return True

    def _principal(self, item: dict[str, Any]) -> dict[str, Any] | None:
        claims = item.get("claims")
        if not isinstance(claims, dict) or claims.get(_MANAGED_CLAIM) is not True:
            return None
        tenant_id = str(claims.get(_TENANT_CLAIM) or "")
        key_id = str(item.get("id") or "")
        if not tenant_id or not key_id or item.get("revoked") or item.get("expired"):
            return None
        scopes = [str(scope) for scope in (item.get("scopes") or [])]
        if any(scope not in VALID_SCOPES for scope in scopes):
            return None
        return {"tenant_id": tenant_id, "scopes": scopes, "key_id": key_id}

    @staticmethod
    def _is_managed_for_tenant(item: dict[str, Any], tenant_id: str) -> bool:
        claims = item.get("claims")
        return (
            isinstance(claims, dict)
            and claims.get(_MANAGED_CLAIM) is True
            and str(claims.get(_TENANT_CLAIM) or "") == str(tenant_id)
        )

    @staticmethod
    def _metadata(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "key_id": str(item.get("id") or ""),
            "name": str(item.get("name") or "Doomberg agent key"),
            "scopes": [str(scope) for scope in (item.get("scopes") or [])],
            "created_at": _iso_from_milliseconds(item.get("created_at")),
            "last_used_at": _iso_from_milliseconds(item.get("last_used_at")),
            "revoked": bool(item.get("revoked")),
            "expired": bool(item.get("expired")),
            "managed_by": "clerk",
        }

    def _require_subject_tenant(self, subject: str, tenant_id: str) -> None:
        if not self._subject_belongs_to_tenant(subject, tenant_id):
            raise ValueError("Clerk user is not linked to this Doomberg tenant")

    def _subject_belongs_to_tenant(self, subject: str, tenant_id: str) -> bool:
        row = self._db.conn.execute(
            "SELECT u.tenant_id FROM oauth_accounts oa "
            "JOIN users u ON u.id = oa.user_id "
            "WHERE oa.provider = ? AND oa.provider_id = ?",
            ("clerk", str(subject)),
        ).fetchone()
        return row is not None and str(row["tenant_id"]) == str(tenant_id)


class AgentKeyStore:
    """Migration-safe facade: Clerk for new keys, local verification for old keys."""

    def __init__(self, legacy: AuthStore, clerk: ClerkManagedApiKeyStore | None = None) -> None:
        self.legacy = legacy
        self.clerk = clerk

    @property
    def uses_clerk(self) -> bool:
        return self.clerk is not None

    def verify(self, secret: str) -> dict[str, Any] | None:
        if secret.startswith("ak_") and self.clerk is not None:
            return self.clerk.verify(secret)
        return self.legacy.verify(secret)

    def mint_key(
        self,
        tenant_id: str,
        scopes: list[str],
        *,
        subject: str | None = None,
    ) -> tuple[str, str]:
        if self.clerk is None:
            return self.legacy.mint_key(tenant_id, scopes)
        if not subject:
            raise ValueError("Clerk subject is required to create an API key")
        return self.clerk.create_key(subject=subject, tenant_id=tenant_id, scopes=scopes)

    def list_keys(self, tenant_id: str, *, subject: str | None = None) -> list[dict[str, Any]]:
        legacy = self.legacy.list_keys(tenant_id)
        if self.clerk is None:
            return legacy
        if not subject:
            raise ValueError("Clerk subject is required to list API keys")
        return self.clerk.list_keys(subject=subject, tenant_id=tenant_id) + legacy

    def revoke_key(
        self,
        key_id: str,
        *,
        tenant_id: str,
        subject: str | None = None,
    ) -> bool:
        if key_id.startswith("ak_") and self.clerk is not None:
            if not subject:
                raise ValueError("Clerk subject is required to revoke an API key")
            return self.clerk.revoke_key(key_id=key_id, subject=subject, tenant_id=tenant_id)
        owned = {item["key_id"] for item in self.legacy.list_keys(tenant_id)}
        return key_id in owned and self.legacy.revoke_key(key_id)


def build_agent_key_store(db: Db) -> AgentKeyStore:
    legacy = AuthStore(db)
    secret_key = os.environ.get("CLERK_SECRET_KEY", "").strip()
    if not secret_key:
        return AgentKeyStore(legacy)
    clerk = ClerkManagedApiKeyStore(
        db,
        secret_key,
        api_url=os.environ.get("CLERK_API_URL", "https://api.clerk.com/v1"),
        api_version=os.environ.get("CLERK_API_VERSION", "2026-05-12"),
        timeout_s=float(os.environ.get("CLERK_API_TIMEOUT_S", "5")),
    )
    return AgentKeyStore(legacy, clerk)
