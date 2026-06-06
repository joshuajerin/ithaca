"""Backend startup smoke test.

Catches the failure mode where a declared Python dependency is unsatisfiable or
silently never installed (e.g. an unsatisfiable ``yfinance`` pin) so the FastAPI
app crashes at import and every terminal request returns a 502 — a failure that
today only surfaces when a real user sends a chat message and gets no reply.

Runnable two ways:
    python artifacts/api-server/tests/test_smoke.py   # standalone
    pytest artifacts/api-server/tests/test_smoke.py    # if pytest installed

It verifies (1) every declared third-party dependency imports, (2) the FastAPI
``app`` object imports cleanly (which pulls in the whole transitive import graph,
including ``worker -> sources.fundamentals -> yfinance`` and
``sources.news -> feedparser``), and (3) ``GET /api/healthz`` and
``POST /api/orchestrate`` round-trip with a 200 through the real ASGI stack
(``TestClient`` runs the app lifespan, so the data worker starts/stops too).
"""
from __future__ import annotations

import importlib
import os
import sys

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

# Declared runtime dependencies (pyproject.toml [project].dependencies) mapped to
# the module name you actually import. ``yfinance`` and ``feedparser`` are the
# ones that have silently failed to install before, but checking the whole set
# means any future bad pin fails here instead of in production.
_DECLARED_IMPORTS = {
    "fastapi": "fastapi",
    "feedparser": "feedparser",
    "httpx": "httpx",
    "openai": "openai",
    "psycopg": "psycopg",
    "psycopg-pool": "psycopg_pool",
    "pydantic": "pydantic",
    "uvicorn": "uvicorn",
    "yfinance": "yfinance",
}


def test_declared_dependencies_import():
    """Every dependency declared in pyproject.toml must actually import."""
    failed = {}
    for dist, module in sorted(_DECLARED_IMPORTS.items()):
        try:
            importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001
            failed[dist] = repr(exc)
    assert not failed, f"declared dependencies failed to import: {failed}"


def test_app_imports_cleanly():
    """Importing the app exercises the full transitive import graph."""
    from app.main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/healthz" in paths, "healthz route missing from app"
    assert "/api/orchestrate" in paths, "orchestrate route missing from app"


def test_endpoints_round_trip():
    """healthz + orchestrate must answer 200 (never the 502 a dead app gives).

    Both checks share one ``TestClient`` so the app lifespan (data worker) starts
    and stops exactly once. The AI path inside ``orchestrate`` is disabled so the
    round-trip is fast and deterministic and falls through to the heuristic
    builder; ``orchestrate`` already swallows AI failures, so a live AI client
    would still return 200 — only slower.

    The orchestrate probe uses a definitional question. That keeps the round-trip
    self-contained (it answers from the heuristic question path instead of firing
    a full-market data fetch), so the smoke test stays fast and network-light
    while still proving the chat endpoint round-trips end to end. A dead or
    crash-looping app — the actual failure this test guards against — cannot
    answer 200 to *any* query.
    """
    from fastapi.testclient import TestClient

    from app import ai, worker
    from app.main import app

    # Run the real lifespan (so dynamic-skill loading and worker start/stop wiring
    # are exercised) but neutralize the background data worker: its staggered
    # network-ingestion loops are not what this smoke test verifies, and firing
    # them would make the test slow and flaky. The worker module is still imported
    # by ``app.main``, so an import-time failure inside it is caught by
    # ``test_app_imports_cleanly``. The endpoints answer from already-ingested DB
    # rows (or the deterministic mock fallback) either way.
    async def _noop_worker(*_args, **_kwargs):
        return None

    original_ai_available = ai.ai_available
    original_worker_start = worker.start
    original_worker_stop = worker.stop
    ai.ai_available = lambda: False  # type: ignore[assignment]
    worker.start = _noop_worker  # type: ignore[assignment]
    worker.stop = _noop_worker  # type: ignore[assignment]
    try:
        with TestClient(app) as client:
            health = client.get("/api/healthz")
            assert health.status_code == 200, (
                f"healthz returned {health.status_code}: {health.text[:300]}"
            )
            assert health.json().get("status") == "ok"

            chat = client.post(
                "/api/orchestrate",
                json={"query": "What is a Sortino ratio?", "sessionId": "default"},
            )
            assert chat.status_code == 200, (
                f"orchestrate returned {chat.status_code}: {chat.text[:300]}"
            )
            body = chat.json()
            assert body.get("sessionId"), f"orchestrate response missing sessionId: {body}"
            # A build returns panels; a question returns an answer. Either proves
            # the chat backend round-tripped.
            assert ("panels" in body) or body.get("answer"), (
                f"orchestrate response missing panels/answer: {body}"
            )
    finally:
        ai.ai_available = original_ai_available  # type: ignore[assignment]
        worker.start = original_worker_start  # type: ignore[assignment]
        worker.stop = original_worker_stop  # type: ignore[assignment]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
