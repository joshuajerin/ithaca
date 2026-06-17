"""Test fixtures + import-path fallback.

In the integrated workspace, ``doomberg_contracts``, ``doomberg_platform``, and
``doomberg_rest`` are installed editable into the shared venv, so the path-insertion below
is a no-op. When running the suite in isolation, we add the source roots so imports resolve.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ensure_importable() -> None:
    candidates = [
        _REPO_ROOT / "packages" / "contracts" / "py",
        _REPO_ROOT / "doomberg-core" / "src",
        _REPO_ROOT / "services" / "platform" / "src",
        _REPO_ROOT / "services" / "control-plane" / "src",
        _REPO_ROOT / "services" / "rest-gateway" / "src",
    ]
    for path in candidates:
        sp = str(path)
        if path.exists() and sp not in sys.path:
            sys.path.insert(0, sp)


_ensure_importable()

from doomberg_platform import open_db  # noqa: E402

from doomberg_rest import create_app  # noqa: E402


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
