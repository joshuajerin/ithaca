from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_gate() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "scripts" / "launch_gate.py"
    spec = importlib.util.spec_from_file_location("doomberg_launch_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _json_payload(output: str) -> dict:
    start = output.index("{")
    return json.loads(output[start:])


def test_launch_gate_local_mode_passes_without_external_services(capsys, monkeypatch):
    monkeypatch.delenv("DOOMBERG_IBKR_ENGINE_URL", raising=False)
    gate = _load_gate()

    code = gate.main(["--mode", "local", "--db", ":memory:", "--skip-ibkr", "--json"])

    assert code == 0
    body = _json_payload(capsys.readouterr().out)
    assert body["ok"] is True
    statuses = {row["name"]: row["status"] for row in body["results"]}
    assert statuses["platform migration"] == "pass"
    assert statuses["rest unauthorized rejection"] == "pass"
    assert statuses["session create"] == "pass"
    assert statuses["event replay"] == "pass"
    assert statuses["artifact fetch"] == "pass"
    assert statuses["mcp unauthorized rejection"] == "pass"
    assert statuses["mcp initialize"] == "pass"
    assert statuses["mcp resource list"] == "pass"
    assert statuses["mcp resource templates"] == "pass"
    assert statuses["mcp resource catalog"] == "pass"
    assert statuses["mcp resource scope denial"] == "pass"
    assert statuses["ibkr smoke"] == "skip"
    catalog = next(row for row in body["results"] if row["name"] == "mcp resource catalog")
    assert catalog["evidence"]["count"] >= 50


def test_launch_gate_can_require_ibkr_smoke(capsys, monkeypatch):
    monkeypatch.delenv("DOOMBERG_IBKR_ENGINE_URL", raising=False)
    gate = _load_gate()

    code = gate.main(["--mode", "local", "--db", ":memory:", "--require-ibkr", "--json"])

    assert code == 1
    body = _json_payload(capsys.readouterr().out)
    assert body["ok"] is False
    ibkr = next(row for row in body["results"] if row["name"] == "ibkr smoke")
    assert ibkr["status"] == "fail"
    assert ibkr["evidence"]["code"] == "BROKER_CONNECTION_REQUIRED"
