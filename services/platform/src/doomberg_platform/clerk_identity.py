"""Shared, framework-neutral Clerk JWT verification and identity resolution.

REST sessions and hosted MCP OAuth access tokens deliberately use the same verifier.  The
module contains no FastAPI or MCP imports so callers can consistently translate the small
set of typed failures into their own protocol responses.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Collection, Literal, Mapping

import jwt
from jwt import ExpiredSignatureError, ImmatureSignatureError, InvalidAudienceError, InvalidIssuerError, InvalidTokenError, PyJWKClient


class ClerkAuthError(RuntimeError):
    """Base class for a Clerk identity failure safe to report generically."""


class ClerkAuthConfigurationError(ClerkAuthError):
    """Required local Clerk configuration is absent or invalid."""


class ClerkTokenInvalid(ClerkAuthError):
    """A presented token cannot be used for this request."""


class ClerkIdentityUnavailable(ClerkAuthError):
    """Signing keys or identity infrastructure could not be reached."""


@dataclass(frozen=True)
class VerifiedClerkIdentity:
    subject: str
    token_type: Literal["session", "oauth"]
    client_id: str | None
    scopes: frozenset[str]
    expires_at: int
    claims: Mapping[str, object]


@dataclass(frozen=True)
class ResolvedClerkPrincipal:
    user_id: str
    tenant_id: str
    subject: str
    claims: Mapping[str, object]


def _env_public_key() -> str | None:
    raw = os.environ.get("CLERK_PEM_PUBLIC_KEY") or os.environ.get("CLERK_JWT_PUBLIC_KEY")
    if not raw:
        return None
    raw = raw.replace("\\n", "\n").strip()
    if "BEGIN PUBLIC KEY" in raw:
        return raw
    return f"-----BEGIN PUBLIC KEY-----\n{raw}\n-----END PUBLIC KEY-----"


def _env_jwks_url() -> str | None:
    explicit = os.environ.get("CLERK_JWKS_URL", "").strip()
    if explicit:
        return explicit
    frontend_api = os.environ.get("CLERK_FRONTEND_API_URL", "").strip().rstrip("/")
    return f"{frontend_api}/.well-known/jwks.json" if frontend_api else None


def _normalize_scopes(claims: Mapping[str, object]) -> frozenset[str]:
    raw = claims.get("scope", claims.get("scopes", ()))
    if isinstance(raw, str):
        return frozenset(part for part in raw.split() if part)
    if isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset(str(part) for part in raw if str(part))
    return frozenset()


class ClerkIdentityService:
    """Verify Clerk tokens locally and resolve Clerk subjects to Doomberg principals.

    ``PyJWKClient`` owns a JWKS cache and refreshes when it encounters an unknown ``kid``.
    Construct this object once per process (the REST app and MCP gateway do this at startup)
    so normal requests never fetch Clerk signing keys.
    """

    def __init__(
        self,
        *,
        issuer: str | None = None,
        pem_public_key: str | None = None,
        jwks_url: str | None = None,
        db: Any | None = None,
        users: Any | None = None,
        auth: Any | None = None,
    ) -> None:
        self.issuer = (issuer if issuer is not None else os.environ.get("CLERK_ISSUER", "")).strip() or None
        self.pem_public_key = pem_public_key if pem_public_key is not None else _env_public_key()
        self.jwks_url = jwks_url if jwks_url is not None else _env_jwks_url()
        self.db = db
        self.users = users
        self.auth = auth
        self._jwks = PyJWKClient(self.jwks_url) if self.jwks_url else None

    @classmethod
    def from_environment(cls, **kwargs: Any) -> "ClerkIdentityService":
        return cls(**kwargs)

    def validate_configuration(self, *, require_issuer: bool = True) -> None:
        if require_issuer and not self.issuer:
            raise ClerkAuthConfigurationError("CLERK_ISSUER is required")
        if not self.pem_public_key and not self._jwks:
            raise ClerkAuthConfigurationError("CLERK_PEM_PUBLIC_KEY or CLERK_JWKS_URL is required")

    def _decode(self, token: str, *, audience: str | None = None) -> dict[str, Any]:
        self.validate_configuration(require_issuer=False)
        try:
            key: Any = self.pem_public_key
            if key is None:
                assert self._jwks is not None
                key = self._jwks.get_signing_key_from_jwt(token).key
            options = {"verify_aud": audience is not None}
            return jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.issuer if self.issuer else None,
                audience=audience,
                options=options,
            )
        except InvalidIssuerError as exc:
            raise ClerkTokenInvalid("invalid Clerk issuer") from exc
        except InvalidAudienceError as exc:
            raise ClerkTokenInvalid("invalid Clerk audience") from exc
        except ExpiredSignatureError as exc:
            raise ClerkTokenInvalid("Clerk token expired") from exc
        except ImmatureSignatureError as exc:
            raise ClerkTokenInvalid("Clerk token is not active") from exc
        except InvalidTokenError as exc:
            raise ClerkTokenInvalid("invalid Clerk token") from exc
        except ClerkAuthError:
            raise
        except Exception as exc:
            # Network and JWKS parsing errors must not be mistaken for a bad user token.
            raise ClerkIdentityUnavailable("Clerk signing keys are unavailable") from exc

    @staticmethod
    def _identity(claims: Mapping[str, object], token_type: Literal["session", "oauth"]) -> VerifiedClerkIdentity:
        subject = str(claims.get("sub") or "").strip()
        if not subject:
            raise ClerkTokenInvalid("Clerk token missing subject")
        try:
            expires_at = int(claims["exp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ClerkTokenInvalid("Clerk token missing expiry") from exc
        client_id = claims.get("client_id") or claims.get("azp")
        return VerifiedClerkIdentity(
            subject=subject,
            token_type=token_type,
            client_id=str(client_id) if client_id else None,
            scopes=_normalize_scopes(claims),
            expires_at=expires_at,
            claims=dict(claims),
        )

    def verify_session_token(
        self, token: str, *, allowed_origins: Collection[str]
    ) -> VerifiedClerkIdentity:
        claims = self._decode(token)
        if claims.get("sts") == "pending":
            raise ClerkTokenInvalid("Clerk session is pending")
        allowed = set(allowed_origins)
        if allowed and claims.get("azp") not in allowed:
            raise ClerkTokenInvalid("invalid Clerk authorized party")
        return self._identity(claims, "session")

    def verify_oauth_token(
        self, token: str, *, audience: str | None = None, required_scopes: Collection[str]
    ) -> VerifiedClerkIdentity:
        self.validate_configuration(require_issuer=True)
        claims = self._decode(token, audience=audience)
        # Clerk's dynamic-client OAuth access tokens do not include an ``aud`` claim even
        # when the client sends the MCP Resource Indicator.  Requiring one here rejects
        # every credential that Codex/Claude Code correctly persisted.  Keep the
        # issuer/signature/expiry checks above, and require the OAuth-only client identifier
        # plus the server's admission scope below so a browser session JWT cannot be used as
        # an MCP bearer token.
        if not str(claims.get("client_id") or "").strip():
            raise ClerkTokenInvalid("Clerk OAuth token missing client id")
        identity = self._identity(claims, "oauth")
        missing = set(required_scopes).difference(identity.scopes)
        if missing:
            raise ClerkTokenInvalid("required OAuth scope is missing")
        return identity

    def resolve_user_and_tenant(self, identity: VerifiedClerkIdentity) -> ResolvedClerkPrincipal:
        if self.db is None or self.users is None or self.auth is None:
            raise ClerkAuthConfigurationError("identity resolver has no platform stores")
        claims = identity.claims
        email = str(
            claims.get("email")
            or claims.get("email_address")
            or claims.get("primary_email_address")
            or f"{identity.subject}@clerk.doomberg.local"
        ).strip().lower()
        name = str(
            claims.get("name")
            or claims.get("full_name")
            or claims.get("username")
            or claims.get("first_name")
            or email
        )
        avatar_url = claims.get("picture") or claims.get("image_url")
        try:
            with self.db.system_scope():
                linked = self.db.conn.execute(
                    "SELECT user_id FROM oauth_accounts WHERE provider=? AND provider_id=?",
                    ("clerk", identity.subject),
                ).fetchone()
                if linked:
                    existing = self.users.get_by_id(linked["user_id"])
                    tenant_id = existing["tenant_id"] if existing else self.auth.create_tenant(name)
                else:
                    by_email = self.db.conn.execute(
                        "SELECT tenant_id FROM users WHERE email=?", (email,)
                    ).fetchone()
                    tenant_id = by_email["tenant_id"] if by_email else self.auth.create_tenant(name)
                user = self.users.oauth_upsert(
                    "clerk", identity.subject, email, name,
                    str(avatar_url) if avatar_url else None, tenant_id,
                )
        except Exception as exc:
            raise ClerkIdentityUnavailable("could not resolve Clerk identity") from exc
        return ResolvedClerkPrincipal(
            user_id=str(user["id"]), tenant_id=str(user["tenant_id"]),
            subject=identity.subject, claims=claims,
        )
