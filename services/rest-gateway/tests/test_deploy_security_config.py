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


def test_dedicated_backtest_workers_are_opt_in_for_production() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()
    worker_manifest = (REPO_ROOT / "infra" / "k8s" / "worker-deployment.yaml").read_text()

    assert 'BACKTEST_WORKER_ENABLED="0"' in deploy_script
    assert 'DOOMBERG_ENABLE_BACKTEST_LOOP="1"' in deploy_script
    assert 'if [[ "${DEPLOY_ENV}" == "prod" && "${BACKTEST_WORKER_ENABLED}" == "1" ]]' in deploy_script
    assert 'if [[ "${BACKTEST_WORKER_ENABLED:-0}" == "1" ]]; then' in workflow
    assert 'value: "${DOOMBERG_ENABLE_BACKTEST_LOOP}"' in worker_manifest
