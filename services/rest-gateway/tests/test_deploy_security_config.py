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


def test_deploy_requires_and_injects_clerk_secret_for_managed_api_keys() -> None:
    deploy_script = (REPO_ROOT / "deploy" / "deploy_services.sh").read_text()
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-do.yml").read_text()
    manifest = (REPO_ROOT / "infra" / "k8s" / "app-deployment.yaml").read_text()

    assert "CLERK_SECRET_KEY must be set for Clerk-managed agent API keys" in deploy_script
    assert '--from-literal=clerk_secret_key="${CLERK_SECRET_KEY}"' in deploy_script
    assert "require_env CLERK_SECRET_KEY" in workflow
    assert "CLERK_SECRET_KEY: ${{ secrets.CLERK_SECRET_KEY }}" in workflow
    assert manifest.count("name: CLERK_SECRET_KEY") == 3
