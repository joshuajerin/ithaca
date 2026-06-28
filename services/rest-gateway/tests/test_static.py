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
        # OAuth providers redirect to a real path before React takes over.
        callback = c.get("/auth/callback")
        assert callback.status_code == 200
        assert "doomberg" in callback.text
        # A built asset is served.
        assert c.get("/assets/app.js").status_code == 200
        # /healthz still wins over the SPA mount.
        assert c.get("/healthz").json() == {"status": "ok"}
        # /api/* still wins (tenant required => 400, NOT the SPA's index.html).
        assert c.get("/api/runs").status_code == 400


def test_no_build_dir_means_no_mount(tmp_path, db, monkeypatch):
    # A non-existent dist dir => the mount is skipped, the API still works.
    monkeypatch.setenv("DOOMBERG_WEB_DIST", str(tmp_path / "does-not-exist"))
    app = create_app(db)
    with TestClient(app) as c:
        assert c.get("/healthz").json() == {"status": "ok"}
        # No SPA mount => the root path is a 404 (no catch-all).
        assert c.get("/").status_code == 404
