"""Small structural contracts for the locked Checkov security gate."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BOOTSTRAP_WORKFLOW = ROOT / ".github" / "workflows" / "bootstrap-cloud-one.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
CHECKOV_PROJECT = ROOT / "tools" / "checkov" / "pyproject.toml"
CHECKOV_LOCK = ROOT / "tools" / "checkov" / "uv.lock"


def workflow_job(workflow: str, name: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-zA-Z0-9_-]+:\n|\Z)", workflow)
    assert match is not None
    return match.group(0)


def test_checkov_tool_is_separately_pinned_and_locked() -> None:
    project = tomllib.loads(CHECKOV_PROJECT.read_text(encoding="utf-8"))
    lock = tomllib.loads(CHECKOV_LOCK.read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    checkov_pin = next(dependency for dependency in dependencies if dependency.startswith("checkov=="))
    locked_checkov = next(package for package in lock["package"] if package["name"] == "checkov")

    assert project["project"]["requires-python"] == ">=3.13,<3.14"
    assert checkov_pin.removeprefix("checkov==") == locked_checkov["version"]


def test_ci_requires_secretless_checkov_job_and_retains_evidence() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    job = workflow_job(workflow, "iac-security")
    assert "aws-actions/configure-aws-credentials" not in job
    assert "actions/create-github-app-token" not in job
    assert "uv sync --project tools/checkov --frozen" in job
    assert "bash scripts/check-iac-security.sh" in job
    assert "if: ${{ always() }}" in job
    assert "retention-days: 14" in job
    gate_job = workflow_job(workflow, "required")
    assert "iac-security" in gate_job


def test_privileged_plan_workflows_scan_and_bind_checkov_evidence() -> None:
    for workflow_path in (BOOTSTRAP_WORKFLOW, DEPLOY_WORKFLOW):
        workflow = workflow_path.read_text(encoding="utf-8")
        plan_job = workflow_job(workflow, "plan")

        assert "uv sync --project tools/checkov --frozen" in plan_job
        assert "bash scripts/check-iac-security.sh" in plan_job
        assert "if: ${{ always() }}" in plan_job
        assert ".artifacts/checkov/" in plan_job
        assert plan_job.index("bash scripts/check-iac-security.sh") < plan_job.index(
            "tofu -chdir=infra/cloud-one plan"
        )
