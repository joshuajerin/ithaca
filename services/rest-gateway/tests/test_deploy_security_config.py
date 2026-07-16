from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_deploy_script_requires_clerk_issuer() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()

    assert ': "${CLERK_ISSUER:?CLERK_ISSUER must be set for ${DEPLOY_ENV}}"' in deploy_script


def test_deploy_workflow_preflight_requires_clerk_issuer() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()

    assert "CLERK_ISSUER: ${{ vars.CLERK_ISSUER }}" in workflow
    assert "require_env CLERK_ISSUER" in workflow


def test_application_image_cannot_build_without_clerk_browser_config() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    build_script = (REPO_ROOT / "deploy" / "build_and_push.sh").read_text()
    checks_workflow = (
        REPO_ROOT / ".github" / "workflows" / "deploy-checks.yml"
    ).read_text()
    parity_workflow = (
        REPO_ROOT / ".github" / "workflows" / "prod-parity.yml"
    ).read_text()
    deploy_workflow = (
        REPO_ROOT / ".github" / "workflows" / "deploy-do.yml"
    ).read_text()

    assert "CLERK_PUBLISHABLE_VALUE must be a Clerk pk_test_ or pk_live_" in dockerfile
    assert 'grep -R -F "${CLERK_PUBLISHABLE_VALUE}" /app/web/dist/assets' in dockerfile
    assert '! grep -R -i -F "Doomberg" /app/web/dist' in dockerfile
    assert "CLERK_PUBLISHABLE_KEY before building Ithaca" in build_script
    assert "CLERK_PUBLISHABLE_VALUE=pk_test_Y2kuZXhhbXBsZS5jb20k" in checks_workflow
    assert "CLERK_PUBLISHABLE_VALUE=pk_test_Y2kuZXhhbXBsZS5jb20k" in parity_workflow
    assert "CLERK_PUBLISHABLE_KEY must start with pk_test_ or pk_live_" in deploy_workflow


def test_deploy_workflow_uses_platform_db_secret() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()

    assert "ITHACA_PLATFORM_DB_URL: ${{ secrets.ITHACA_PLATFORM_DB_URL }}" in workflow
    assert "require_env ITHACA_PLATFORM_DB_URL" in workflow
    assert "ITHACA_ARCHIVE_URL" not in workflow


def test_deploy_restarts_consumers_when_ithaca_secret_changes() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()
    kill_switch_lib = (
        REPO_ROOT / "deploy" / "lib" / "execution_kill_switch.sh"
    ).read_text()

    assert 'gateway_db_secret_before="$(secret_checksum' in deploy_script
    assert 'worker_db_secret_before="$(secret_checksum' in deploy_script
    assert 'rollout restart deployment/ithaca-app' in deploy_script
    assert 'rollout restart deployment/ithaca-workers' in deploy_script
    assert 'resolve_execution_kill_switch "${K8S_GATEWAY_NAMESPACE}"' in deploy_script
    assert 'preserving existing execution kill-switch value' in kill_switch_lib
    assert 'refusing to default it off' in kill_switch_lib
    assert '--ignore-not-found' in kill_switch_lib
    assert 'requested="${requested:-0}"' in kill_switch_lib

    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()
    assert workflow.count(
        "ITHACA_EXECUTION_KILL_SWITCH: ${{ vars.ITHACA_EXECUTION_KILL_SWITCH }}"
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


def test_mcp_gateway_receives_the_platform_database_secret() -> None:
    manifest = (REPO_ROOT / "infra" / "k8s" / "app-deployment.yaml").read_text()

    mcp_gateway = manifest.split('name: mcp-gateway', 1)[1]
    ithaca_db = mcp_gateway.split('- name: ITHACA_DB', 1)[1].split('- name: DOOMBERG_DB', 1)[0]
    assert 'secretKeyRef:' in ithaca_db
    assert 'name: ithaca-db' in ithaca_db
    assert 'key: platform_url' in ithaca_db


def test_dedicated_backtest_workers_are_opt_in_for_production() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()
    worker_manifest = (REPO_ROOT / "infra" / "k8s" / "worker-deployment.yaml").read_text()

    assert 'BACKTEST_WORKER_ENABLED="0"' in deploy_script
    assert 'ITHACA_ENABLE_BACKTEST_LOOP="1"' in deploy_script
    assert 'if [[ "${DEPLOY_ENV}" == "prod" && "${BACKTEST_WORKER_ENABLED}" == "1" ]]' in deploy_script
    assert 'if [[ "${BACKTEST_WORKER_ENABLED:-0}" == "1" ]]; then' in workflow
    assert 'value: "${ITHACA_ENABLE_BACKTEST_LOOP}"' in worker_manifest


def test_app_rollout_does_not_require_surge_capacity() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()
    app_manifest = (REPO_ROOT / "infra" / "k8s" / "app-deployment.yaml").read_text()

    assert 'APP_MAX_SURGE="${APP_MAX_SURGE:-0}"' in deploy_script
    assert 'APP_MAX_UNAVAILABLE="${APP_MAX_UNAVAILABLE:-1}"' in deploy_script
    assert "maxSurge: ${APP_MAX_SURGE}" in app_manifest
    assert "maxUnavailable: ${APP_MAX_UNAVAILABLE}" in app_manifest
