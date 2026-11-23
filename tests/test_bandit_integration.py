"""Structural contracts for the required, secretless Bandit CI gate."""

import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BANDIT_PROJECT = ROOT / "tools" / "bandit" / "pyproject.toml"
BANDIT_LOCK = ROOT / "tools" / "bandit" / "uv.lock"
ROOT_PROJECT = ROOT / "pyproject.toml"
BANDIT_RUNNER = ROOT / "scripts" / "run-bandit.sh"


def workflow_job(workflow: str, name: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-zA-Z0-9_-]+:\n|\Z)", workflow)
    assert match is not None
    return match.group(0)


def test_bandit_tool_is_separately_pinned_and_locked() -> None:
    project = tomllib.loads(BANDIT_PROJECT.read_text(encoding="utf-8"))
    lock = tomllib.loads(BANDIT_LOCK.read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    bandit_pin = next(dependency for dependency in dependencies if dependency.startswith("bandit=="))
    locked_bandit = next(package for package in lock["package"] if package["name"] == "bandit")

    assert project["project"]["requires-python"] == ">=3.13,<3.14"
    assert project["tool"]["uv"]["exclude-newer"] == "7 days"
    assert bandit_pin.removeprefix("bandit==") == locked_bandit["version"]


def test_ci_requires_secretless_bandit_with_explicit_thresholds() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    job = workflow_job(workflow, "bandit")

    assert "actions/create-github-app-token" not in job
    assert "setup-python-project" not in job
    assert "secrets." not in job
    assert "github.event.pull_request.head.repo.full_name" not in job
    assert "uv sync --project tools/bandit --locked" in job
    assert "scripts/run-bandit.sh" in job
    assert "--exit-zero" not in job

    runner = BANDIT_RUNNER.read_text(encoding="utf-8")
    assert "targets=(src/ backend/ scripts/ infra/scripts/)" in runner
    assert "-c pyproject.toml" in runner
    assert "--severity-level medium" in runner
    assert "--confidence-level medium" in runner
    assert "--exit-zero" not in runner

    required = workflow_job(workflow, "required")
    assert "- bandit" in required
    assert "BANDIT_RESULT: ${{ needs.bandit.result }}" in required
    assert 'require_result bandit "${BANDIT_RESULT}" success' in required

    test_job = workflow_job(workflow, "test")
    assert "uv sync --project tools/bandit --locked" in test_job


def test_bandit_policy_has_no_blanket_rule_skip() -> None:
    project = tomllib.loads(ROOT_PROJECT.read_text(encoding="utf-8"))

    assert "skips" not in project["tool"]["bandit"]


def test_bandit_threshold_rejects_a_credible_shell_injection(tmp_path: Path) -> None:
    unsafe_source = tmp_path / "unsafe_shell.py"
    unsafe_source.write_text(
        "import subprocess\n\n"
        "def run(command: str) -> None:\n"
        "    subprocess.run(command, shell=True, check=True)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(BANDIT_RUNNER), str(unsafe_source)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "B602" in result.stdout + result.stderr
