"""The rest-gateway serves the built web UI from the same backend (one LB for UI + API).

The SPA is mounted at ``/`` but LAST, so ``/api/*`` and ``/healthz`` always take precedence.
We point ``DOOMBERG_WEB_DIST`` at a throwaway build so the test is deterministic regardless
of whether ``web/dist`` has actually been compiled.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from doomberg_rest import create_app


def test_spa_served_and_api_precedence(tmp_path, db, monkeypatch):
    # A throwaway "build".
    (tmp_path / "index.html").write_text("<!doctype html><title>doomberg</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('hi')")
    monkeypatch.setenv("DOOMBERG_WEB_DIST", str(tmp_path))

    app = create_app(db)
    with TestClient(app) as c:
        # SPA index at root.
        root = c.get("/")
        assert root.status_code == 200
        assert "doomberg" in root.text
        assert root.headers["cache-control"] == "no-store, max-age=0"
        # BrowserRouter deep links fall back to the SPA shell.
        sessions = c.get("/sessions")
        assert sessions.status_code == 200
        assert "doomberg" in sessions.text
        assert sessions.headers["cache-control"] == "no-store, max-age=0"
        # A built asset is served.
        asset = c.get("/assets/app.js")
        assert asset.status_code == 200
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        # Deleted assets must not receive the HTML shell as JavaScript. Browsers reject
        # that MIME mismatch before React can render, leaving a completely blank page.
        missing_asset = c.get("/assets/old-build.js")
        assert missing_asset.status_code == 404
        assert missing_asset.headers["content-type"].startswith("application/json")
        # /healthz still wins over the SPA mount.
        assert c.get("/healthz").json()["ready"] is True
        # /api/* still wins (tenant required => 400, NOT the SPA's index.html).
        assert c.get("/api/runs").status_code == 400
        # Unknown API paths must not be swallowed by the SPA fallback.
        api_missing = c.get("/api/not-a-route")
        assert api_missing.status_code == 404
        assert api_missing.headers["content-type"].startswith("application/json")


def test_no_build_dir_means_no_mount(tmp_path, db, monkeypatch):
    # A non-existent dist dir => the mount is skipped, the API still works.
    monkeypatch.setenv("DOOMBERG_WEB_DIST", str(tmp_path / "does-not-exist"))
    app = create_app(db)
    with TestClient(app) as c:
        assert c.get("/healthz").json()["ready"] is True
        # No SPA mount => the root path is a 404 (no catch-all).
        assert c.get("/").status_code == 404
