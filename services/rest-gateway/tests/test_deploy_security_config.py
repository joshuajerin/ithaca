from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_deploy_script_requires_clerk_issuer() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()

    assert ': "${CLERK_ISSUER:?CLERK_ISSUER must be set for ${DEPLOY_ENV}}"' in deploy_script


def test_deploy_workflow_preflight_requires_clerk_issuer() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()

    assert "CLERK_ISSUER: ${{ vars.CLERK_ISSUER }}" in workflow
    assert "require_env CLERK_ISSUER" in workflow


def test_deploy_workflow_uses_platform_db_secret() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()

    assert "DOOMBERG_PLATFORM_DB_URL: ${{ secrets.DOOMBERG_PLATFORM_DB_URL }}" in workflow
    assert "require_env DOOMBERG_PLATFORM_DB_URL" in workflow
    assert "DOOMBERG_ARCHIVE_URL" not in workflow


def test_deploy_restarts_consumers_when_doomberg_secret_changes() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()
    kill_switch_lib = (
        REPO_ROOT / "deploy" / "lib" / "execution_kill_switch.sh"
    ).read_text()

    assert 'gateway_db_secret_before="$(secret_checksum' in deploy_script
    assert 'worker_db_secret_before="$(secret_checksum' in deploy_script
    assert 'rollout restart deployment/doomberg-app' in deploy_script
    assert 'rollout restart deployment/doomberg-workers' in deploy_script
    assert 'resolve_execution_kill_switch "${K8S_GATEWAY_NAMESPACE}"' in deploy_script
    assert 'preserving existing execution kill-switch value' in kill_switch_lib
    assert 'refusing to default it off' in kill_switch_lib
    assert '--ignore-not-found' in kill_switch_lib
    assert 'requested="${requested:-0}"' in kill_switch_lib

    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()
    assert workflow.count(
        "DOOMBERG_EXECUTION_KILL_SWITCH: ${{ vars.DOOMBERG_EXECUTION_KILL_SWITCH }}"
    ) == 2


def test_deploy_release_gate_checks_readiness_and_worker_heartbeats() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()

    assert '"https://${APP_HOST}/livez"' in workflow
    assert '"https://${APP_HOST}/healthz"' in workflow
    assert '"https://${APP_HOST}/readyz"' in workflow
    assert "--require-workers-ready" in workflow
    assert "--require-active-worker" not in workflow
