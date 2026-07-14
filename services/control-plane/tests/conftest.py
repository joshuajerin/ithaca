"""Test fixtures + import-path fallback for the control plane.

In the integrated workspace, ``ithaca_core`` / ``ithaca_contracts`` / ``ithaca_platform``
and this package are installed editable, so the path-insertion below is a no-op. When running
in isolation we add the package source roots so imports resolve.

Each test gets a fresh in-memory platform and a fresh app whose dependency overrides point at
that platform — so tenant isolation and trace state never leak between tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEST_ROOT = Path(__file__).resolve().parent


def _ensure_importable() -> None:
    candidates = [
        _TEST_ROOT,
        _REPO_ROOT / "packages" / "contracts" / "py",
        _REPO_ROOT / "ithaca-core" / "src",
        _REPO_ROOT / "services" / "platform" / "src",
        _REPO_ROOT / "services" / "control-plane" / "src",
    ]
    for path in candidates:
        sp = str(path)
        if path.exists() and sp not in sys.path:
            sys.path.insert(0, sp)


_ensure_importable()

from fastapi.testclient import TestClient  # noqa: E402

from control_helpers import valid_spec  # noqa: E402
from ithaca_control.app import create_app  # noqa: E402
from ithaca_control.deps import Platform, get_core, get_platform  # noqa: E402
from ithaca_core import Core  # noqa: E402


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("ITHACA_ENV", "test")


@pytest.fixture()
def platform():
    return Platform(":memory:")


@pytest.fixture()
def client(platform):
    app = create_app()
    app.dependency_overrides[get_platform] = lambda: platform
    app.dependency_overrides[get_core] = lambda: Core()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def tenant_a() -> str:
    import uuid

    return str(uuid.uuid4())


@pytest.fixture()
def tenant_b() -> str:
    import uuid

    return str(uuid.uuid4())


@pytest.fixture()
def spec() -> dict:
    return valid_spec()
