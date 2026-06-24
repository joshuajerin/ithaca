"""Test fixtures + import-path fallback.

In the integrated workspace, ``doomberg_contracts`` and ``doomberg_platform`` are installed
editable into the shared venv, so the path-insertion below is a no-op. When running the
suite in isolation (no editable install), we add the package source roots so imports resolve.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ensure_importable() -> None:
    candidates = [
        _REPO_ROOT / "packages" / "contracts" / "py",
        _REPO_ROOT / "services" / "platform" / "src",
    ]
    for path in candidates:
        sp = str(path)
        if path.exists() and sp not in sys.path:
            sys.path.insert(0, sp)


_ensure_importable()

from doomberg_platform import (  # noqa: E402
    JobStore,
    Platform,
    RunStore,
    StrategyStore,
    TraceStore,
    open_db,
)


@pytest.fixture()
def db():
    handle = open_db(":memory:")
    yield handle
    handle.close()


@pytest.fixture()
def trace_store(db):
    return TraceStore(db)


@pytest.fixture()
def run_store(db):
    return RunStore(db)


@pytest.fixture()
def job_store(db):
    return JobStore(db)


@pytest.fixture()
def strategy_store(db):
    return StrategyStore(db)


@pytest.fixture()
def platform(db):
    return Platform(db)
