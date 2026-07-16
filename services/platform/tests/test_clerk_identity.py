from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from doomberg_platform import ClerkIdentityService, ClerkTokenInvalid


@pytest.fixture
def clerk_keys() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


def _token(private: str, **claims: object) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": "user_1", "iss": "https://clerk.example", "exp": int((now + timedelta(minutes=5)).timestamp()), **claims}
    return jwt.encode(payload, private, algorithm="RS256")


def test_verifies_clerk_session_and_authorized_party(clerk_keys: tuple[str, str]) -> None:
    private, public = clerk_keys
    service = ClerkIdentityService(issuer="https://clerk.example", pem_public_key=public)
    identity = service.verify_session_token(_token(private, azp="https://app.tradeithaca.com"), allowed_origins=["https://app.tradeithaca.com"])
    assert identity.subject == "user_1"
    with pytest.raises(ClerkTokenInvalid, match="authorized party"):
        service.verify_session_token(_token(private, azp="https://other.example"), allowed_origins=["https://app.tradeithaca.com"])


def test_verifies_clerk_dynamic_oauth_without_audience_and_normalizes_scopes(clerk_keys: tuple[str, str]) -> None:
    private, public = clerk_keys
    service = ClerkIdentityService(issuer="https://clerk.example", pem_public_key=public)
    identity = service.verify_oauth_token(
        _token(private, client_id="clerk-dcr-client", scope="openid offline_access"),
        required_scopes=["openid"],
    )
    assert identity.scopes == frozenset({"openid", "offline_access"})
    with pytest.raises(ClerkTokenInvalid, match="scope"):
        service.verify_oauth_token(
            _token(private, client_id="clerk-dcr-client", scopes=["profile"]),
            required_scopes=["openid"],
        )
    with pytest.raises(ClerkTokenInvalid, match="client id"):
        service.verify_oauth_token(_token(private, scope="openid"), required_scopes=["openid"])
