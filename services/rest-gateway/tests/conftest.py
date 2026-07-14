"""Test fixtures + import-path fallback.

In the integrated workspace, ``ithaca_contracts``, ``ithaca_platform``, and
``ithaca_rest`` are installed editable into the shared venv, so the path-insertion below
is a no-op. When running the suite in isolation, we add the source roots so imports resolve.
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEST_ROOT = Path(__file__).resolve().parent


def _ensure_importable() -> None:
    candidates = [
        _TEST_ROOT,
        _REPO_ROOT / "packages" / "contracts" / "py",
        _REPO_ROOT / "ithaca-core" / "src",
        _REPO_ROOT / "services" / "platform" / "src",
        _REPO_ROOT / "services" / "control-plane" / "src",
        _REPO_ROOT / "services" / "runtime" / "src",
        _REPO_ROOT / "services" / "rest-gateway" / "src",
    ]
    for path in candidates:
        sp = str(path)
        if path.exists() and sp not in sys.path:
            sys.path.insert(0, sp)


_ensure_importable()

from ithaca_platform import open_db  # noqa: E402

from ithaca_rest import create_app  # noqa: E402


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("ITHACA_ENV", "test")


@pytest.fixture()
def db():
    handle = open_db(":memory:")
    yield handle
    handle.close()


@pytest.fixture()
def app(db):
    return create_app(db)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def stores(app):
    return app.state.stores


@pytest.fixture()
def tenant_a() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def tenant_b() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def clerk_auth(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("CLERK_PEM_PUBLIC_KEY", public_pem)
    monkeypatch.setenv("CLERK_ALLOWED_ORIGINS", "http://localhost:5174,https://app.tradeithaca.com")

    def mint(
        *,
        email: str = "founder@acme.test",
        name: str = "Founder",
        sub: str | None = None,
        azp: str = "http://localhost:5174",
    ) -> str:
        now = int(time.time())
        subject = sub or f"user_{uuid.uuid4().hex}"
        return jwt.encode(
            {
                "sub": subject,
                "email": email,
                "name": name,
                "azp": azp,
                "iat": now,
                "nbf": now - 5,
                "exp": now + 300,
            },
            private_pem,
            algorithm="RS256",
        )

    return mint
