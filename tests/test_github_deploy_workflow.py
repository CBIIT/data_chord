"""Static safety contracts for the Cloud One GitHub workflows."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
BOOTSTRAP_WORKFLOW = ROOT / ".github" / "workflows" / "bootstrap-cloud-one.yml"


def test_release_uses_separate_build_plan_and_protected_apply_environments() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert 'test "${REQUESTED_REF}" = "refs/heads/main"' in workflow
    assert "environment: dev-build" in workflow
    assert "environment: dev-plan" in workflow
    assert "environment: dev\n" in workflow
    assert "managed-session-policies: arn:aws:iam::aws:policy/ReadOnlyAccess" in workflow
    assert "if: inputs.apply" in workflow


def test_release_builds_the_private_dependency_and_deploys_by_digest() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "actions/create-github-app-token@" in workflow
    assert "repositories: agentic_harmonization" in workflow
    assert "--secret id=github_token,env=PRIVATE_DEPENDENCY_TOKEN" in workflow
    assert "imageTag=${GITHUB_SHA}" in workflow
    assert "image_digest" in workflow
    assert "cloud_one_environment.py validate" in workflow
    assert "runtime" in workflow


def test_release_applies_only_the_same_run_reviewed_plan() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    plan_start = workflow.index("\n  plan:\n")
    apply_start = workflow.index("\n  apply:\n")
    assert plan_start < apply_start
    assert "artifact-ids: ${{ needs.plan.outputs.artifact_id }}" in workflow
    assert "${{ needs.plan.outputs.plan_sha256 }}" in workflow
    assert 'test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"' in workflow
    assert 'apply -input=false "../../.plans/dev-runtime.tfplan"' in workflow


def test_bootstrap_is_network_independent_and_approval_gated() -> None:
    workflow = BOOTSTRAP_WORKFLOW.read_text(encoding="utf-8")

    assert "tofu-vars" in workflow
    assert "cbiit dev bootstrap" in workflow
    assert "runtime" not in workflow
    assert "environment: dev-plan" in workflow
    assert "environment: dev\n" in workflow
    assert "if: inputs.apply" in workflow
    assert "artifact-ids: ${{ needs.plan.outputs.artifact_id }}" in workflow
