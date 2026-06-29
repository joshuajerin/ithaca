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
