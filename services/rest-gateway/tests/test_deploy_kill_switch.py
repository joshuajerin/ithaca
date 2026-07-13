from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[3]
LIB = REPO_ROOT / "deploy" / "lib" / "execution_kill_switch.sh"


def _resolve(tmp_path: Path, mode: str, *, requested: str | None = None) -> subprocess.CompletedProcess[str]:
    kubectl = tmp_path / "kubectl"
    kubectl.write_text(
        "#!/usr/bin/env bash\n"
        "case \"${FAKE_KUBECTL_MODE}\" in\n"
        "  active) printf 'MQ==' ;;\n"
        "  absent) exit 0 ;;\n"
        "  failure) echo 'apiserver unavailable' >&2; exit 42 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    kubectl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_KUBECTL_MODE": mode,
    }
    if requested is None:
        env.pop("DOOMBERG_EXECUTION_KILL_SWITCH", None)
    else:
        env["DOOMBERG_EXECUTION_KILL_SWITCH"] = requested
    return subprocess.run(
        [
            "bash",
            "-c",
            f"source {LIB!s}; resolve_execution_kill_switch test-namespace off",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_resolver_preserves_active_cluster_halt(tmp_path: Path):
    result = _resolve(tmp_path, "active")
    assert result.returncode == 0
    assert result.stdout == "1"
    assert "preserving existing" in result.stderr


def test_resolver_defaults_off_only_when_secret_is_absent(tmp_path: Path):
    result = _resolve(tmp_path, "absent")
    assert result.returncode == 0
    assert result.stdout == "0"


def test_resolver_fails_closed_when_cluster_read_fails(tmp_path: Path):
    result = _resolve(tmp_path, "failure")
    assert result.returncode != 0
    assert result.stdout == ""
    assert "refusing to default it off" in result.stderr


def test_resolver_rejects_invalid_explicit_value_without_cluster_read(tmp_path: Path):
    result = _resolve(tmp_path, "failure", requested="yes")
    assert result.returncode != 0
    assert "must be 0 or 1" in result.stderr
    assert "apiserver unavailable" not in result.stderr
