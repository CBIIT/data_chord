"""Static contracts for the locked Checkov security gate."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BOOTSTRAP_WORKFLOW = ROOT / ".github" / "workflows" / "bootstrap-cloud-one.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
CHECKOV_PROJECT = ROOT / "tools" / "checkov" / "pyproject.toml"
CHECKOV_LOCK = ROOT / "tools" / "checkov" / "uv.lock"
CHECKOV_ROOTS = ROOT / "tools" / "checkov" / "roots.txt"
CHECKOV_WRAPPER = ROOT / "scripts" / "check-iac-security.sh"


def test_checkov_tool_is_separately_pinned_and_locked() -> None:
    project = CHECKOV_PROJECT.read_text(encoding="utf-8")
    lock = CHECKOV_LOCK.read_text(encoding="utf-8")

    assert 'checkov==3.4.6' in project
    assert 'requires-python = ">=3.13,<3.14"' in project
    assert 'name = "checkov"' in lock
    assert 'version = "3.4.6"' in lock


def test_checkov_manifest_covers_every_committed_opentofu_root() -> None:
    manifest_directories = {
        line.split("|", maxsplit=2)[1]
        for line in CHECKOV_ROOTS.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    discovered_directories = {
        str(lock.parent.relative_to(ROOT)) for lock in (ROOT / "infra").rglob(".terraform.lock.hcl")
    }

    assert manifest_directories == discovered_directories


def test_checkov_wrapper_is_deterministic_and_evidence_producing() -> None:
    wrapper = CHECKOV_WRAPPER.read_text(encoding="utf-8")

    assert 'uv run --project' not in wrapper
    assert '"${uv_bin}" run --project "${tool_project}" --frozen checkov' in wrapper
    assert "--config-file" in wrapper
    assert "--output json" in wrapper
    assert "--output sarif" in wrapper
    assert "configuration-sha256.txt" in wrapper
    assert "Passed | Failed | Skipped" in wrapper
    assert "The Checkov root manifest does not match" in wrapper
    for field in ("reason=", "ref=", "owner=", "review="):
        assert field in wrapper
    assert "Checkov suppression references a missing file" in wrapper


def test_ci_requires_secretless_checkov_job_and_retains_evidence() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "\n  iac-security:\n" in workflow
    job = workflow[workflow.index("\n  iac-security:\n") : workflow.index("\n  quality:\n")]
    assert "aws-actions/configure-aws-credentials" not in job
    assert "actions/create-github-app-token" not in job
    assert "uv sync --project tools/checkov --frozen" in job
    assert "bash scripts/check-iac-security.sh" in job
    assert "if: ${{ always() }}" in job
    assert "retention-days: 14" in job
    assert "IAC_SECURITY_RESULT" in workflow
    assert 'require_result iac-security "${IAC_SECURITY_RESULT}" success' in workflow


def test_privileged_plan_workflows_scan_and_bind_checkov_evidence() -> None:
    for workflow_path in (BOOTSTRAP_WORKFLOW, DEPLOY_WORKFLOW):
        workflow = workflow_path.read_text(encoding="utf-8")
        plan_start = workflow.index("\n  plan:\n")
        apply_start = workflow.index("\n  apply:\n")
        plan_job = workflow[plan_start:apply_start]

        assert "uv sync --project tools/checkov --frozen" in plan_job
        assert "bash scripts/check-iac-security.sh" in plan_job
        assert "if: ${{ always() }}" in plan_job
        assert ".artifacts/checkov/" in plan_job
        assert plan_job.index("bash scripts/check-iac-security.sh") < plan_job.index("tofu -chdir=infra/cloud-one plan")
