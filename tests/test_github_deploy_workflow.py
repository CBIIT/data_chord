"""Static safety contracts for the Cloud One GitHub workflows."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
BOOTSTRAP_WORKFLOW = ROOT / ".github" / "workflows" / "bootstrap-cloud-one.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = ROOT / "Dockerfile"


def test_release_uses_jobs_for_build_and_plan_and_one_dev_environment() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert 'test "${REQUESTED_REF}" = "refs/heads/main"' in workflow
    assert "environment: dev-build" not in workflow
    assert "environment: dev-plan" not in workflow
    assert workflow.count("environment: dev\n") == 1
    assert "deployer_role_arn" in workflow
    assert "secrets.AWS_ROLE_TO_ASSUME" not in workflow
    assert "managed-session-policies: arn:aws:iam::aws:policy/ReadOnlyAccess" in workflow
    assert "publish_only:" in workflow
    assert 'test "${APPLY}:${PUBLISH_ONLY}" != "true:true"' in workflow
    assert "if: ${{ !inputs.publish_only }}" in workflow
    assert "if: ${{ inputs.apply && !inputs.publish_only }}" in workflow


def test_release_builds_the_private_dependency_and_deploys_by_digest() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "actions/create-github-app-token@" in workflow
    assert "repositories: agentic_harmonization" in workflow
    assert "--provenance=false" in workflow
    assert "--secret id=github_token,env=PRIVATE_DEPENDENCY_TOKEN" in workflow
    assert "imageTag=${GITHUB_SHA}" in workflow
    assert "image_digest" in workflow
    assert "image-scan-complete" in workflow
    assert "DescribeImageScanFindings" in workflow
    assert "ScanNotFoundException" in workflow
    assert 'for attempt in $(seq 1 12)' in workflow
    assert "ECR did not expose the scan within 60 seconds." in workflow
    assert '("CRITICAL", "HIGH")' in workflow
    assert "cloud_one_environment.py validate" in workflow
    assert "runtime" in workflow
    assert "cbiit dev network" not in workflow
    assert workflow.index("\n  build:\n") < workflow.index("\n  plan:\n")
    assert workflow.index("\n  plan:\n") < workflow.index("Require the completed VPC contract")
    assert "Write image publication summary" in workflow
    assert "steps.image.outputs.image_uri" in workflow
    assert "Verify VPC and subnet ownership" in workflow
    assert "AvailabilityZone" in workflow


def test_release_applies_only_the_same_run_reviewed_plan() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    plan_start = workflow.index("\n  plan:\n")
    apply_start = workflow.index("\n  apply:\n")
    assert plan_start < apply_start
    assert "artifact-ids: ${{ needs.plan.outputs.artifact_id }}" in workflow
    assert "${{ needs.plan.outputs.plan_sha256 }}" in workflow
    assert 'test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"' in workflow
    assert 'apply -input=false "../../.plans/dev-runtime.tfplan"' in workflow
    assert "> .plans/dev-runtime.txt" in workflow
    assert "> ../../.plans/dev-runtime.txt" not in workflow
    assert "scripts.cloud_one_smoke" in workflow
    assert "aws ecs run-task" in workflow
    assert "tasks-stopped" in workflow


def test_bootstrap_is_network_independent_and_approval_gated() -> None:
    workflow = BOOTSTRAP_WORKFLOW.read_text(encoding="utf-8")

    assert "tofu-vars" in workflow
    assert "cbiit dev bootstrap" in workflow
    assert "runtime" not in workflow
    assert "environment: dev-plan" not in workflow
    assert workflow.count("environment: dev\n") == 1
    assert "deployer_role_arn" in workflow
    assert "secrets.AWS_ROLE_TO_ASSUME" not in workflow
    assert "if: inputs.apply" in workflow
    assert "artifact-ids: ${{ needs.plan.outputs.artifact_id }}" in workflow
    assert "> .plans/dev-bootstrap.txt" in workflow
    assert "> ../../.plans/dev-bootstrap.txt" not in workflow


def test_bootstrap_and_release_serialize_the_shared_state() -> None:
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP_WORKFLOW.read_text(encoding="utf-8")

    assert "group: data-chord-cbiit-dev\n" in release
    assert "group: data-chord-cbiit-dev\n" in bootstrap


def test_release_base_images_are_pinned_by_digest() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    from_lines = [line for line in dockerfile.splitlines() if line.startswith("FROM ")]

    assert len(from_lines) == 3
    assert all("@sha256:" in line for line in from_lines)
    assert dockerfile.count("public.ecr.aws/amazonlinux/amazonlinux:2023.12.20261016.0-minimal@sha256:") == 2
    assert "python:3.13-slim-bookworm" not in dockerfile
    assert dockerfile.count("--releasever=latest --setopt=install_weak_deps=False") == 2
    for patched_rpm in (
        "python3.13-3.13.16-1.amzn2023.0.1",
        "openssl-libs-3.5.8-1.amzn2023.0.3",
        "pcre2-10.40-1.amzn2023.0.5",
        "expat-2.8.3-1.amzn2023.0.1",
        "rpm-4.16.1.3-29.amzn2023.0.8",
        "libcurl-minimal-8.21.0-5.amzn2023.0.3",
        "libcap-2.73-1.amzn2023.0.8",
    ):
        assert patched_rpm in dockerfile


def test_ci_builds_and_smoke_tests_the_production_container() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "--provenance=false" in workflow
    assert "--secret id=github_token,env=PRIVATE_DEPENDENCY_TOKEN" in workflow
    assert "--tag data-chord:ci" in workflow
    assert "import backend.app.main, numpy, pandas, pyarrow" in workflow
