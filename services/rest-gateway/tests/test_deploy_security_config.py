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


def test_deploy_requires_and_injects_clerk_secret_for_managed_api_keys() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()
    manifest = (REPO_ROOT / "infra" / "k8s" / "app-deployment.yaml").read_text()

    assert "CLERK_SECRET_KEY must be set for Clerk-managed agent API keys" in deploy_script
    assert '--from-literal=clerk_secret_key="${CLERK_SECRET_KEY}"' in deploy_script
    assert "require_env CLERK_SECRET_KEY" in workflow
    assert "CLERK_SECRET_KEY: ${{ secrets.CLERK_SECRET_KEY }}" in workflow
    assert manifest.count("name: CLERK_SECRET_KEY") == 3


def test_dedicated_backtest_workers_are_opt_in_for_production() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()
    worker_manifest = (REPO_ROOT / "infra" / "k8s" / "worker-deployment.yaml").read_text()

    assert 'BACKTEST_WORKER_ENABLED="0"' in deploy_script
    assert 'DOOMBERG_ENABLE_BACKTEST_LOOP="1"' in deploy_script
    assert 'if [[ "${DEPLOY_ENV}" == "prod" && "${BACKTEST_WORKER_ENABLED}" == "1" ]]' in deploy_script
    assert 'if [[ "${BACKTEST_WORKER_ENABLED:-0}" == "1" ]]; then' in workflow
    assert 'value: "${DOOMBERG_ENABLE_BACKTEST_LOOP}"' in worker_manifest
