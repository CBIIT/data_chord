"""Static safety contract for the manually dispatched deployment workflow."""

from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml"
)


def test_plan_precedes_the_protected_same_run_apply() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    plan_start = workflow.index("\n  plan:\n")
    apply_start = workflow.index("\n  apply:\n")
    plan_job = workflow[plan_start:apply_start]

    assert plan_start < apply_start
    assert "environment: ${{ format('{0}-plan', inputs.stage) }}" in plan_job
    assert "arn:aws:iam::aws:policy/ReadOnlyAccess" in plan_job
    assert "artifact-ids: ${{ needs.plan.outputs.artifact_id }}" in workflow
    assert "${{ needs.plan.outputs.plan_sha256 }}" in workflow
    assert "environment: ${{ inputs.stage }}" not in plan_job


def test_only_configured_staging_and_main_can_request_aws_credentials() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    stage_input = workflow[
        workflow.index("      stage:\n") : workflow.index("      apply:\n")
    ]

    assert 'test "${REQUESTED_REF}" = "refs/heads/main"' in workflow
    assert "          - staging" in stage_input
    assert "          - dev" not in stage_input
    assert "          - qa" not in stage_input
    assert "          - prod" not in stage_input
    assert "role-duration-seconds: 14400" in workflow
