"""Static safety contracts for the Cloud One GitHub workflows."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
BOOTSTRAP_WORKFLOW = ROOT / ".github" / "workflows" / "bootstrap-cloud-one.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-image.yml"
PYTHON_SETUP_ACTION = ROOT / ".github" / "actions" / "setup-python-project" / "action.yml"
NODE_SETUP_ACTION = ROOT / ".github" / "actions" / "setup-node-project" / "action.yml"
DOCKERFILE = ROOT / "Dockerfile"


def test_release_uses_read_only_plan_and_one_dev_environment() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert 'test "${REQUESTED_REF}" = "refs/heads/main"' in workflow
    assert "environment: dev-build" not in workflow
    assert "environment: dev-plan" not in workflow
    assert workflow.count("environment: dev\n") == 1
    assert "deployer_role_arn" in workflow
    assert "secrets.AWS_ROLE_TO_ASSUME" not in workflow
    assert "managed-session-policies: arn:aws:iam::aws:policy/ReadOnlyAccess" in workflow
    assert "operation:" in workflow
    assert "- plan\n" in workflow
    assert "- deploy\n" in workflow
    assert workflow.count("- plan\n") == 1
    assert workflow.count("- deploy\n") == 1
    assert "publish_only:" not in workflow
    assert "inputs.apply" not in workflow
    assert "if: ${{ inputs.operation == 'deploy' }}" in workflow
    assert "\n  build:\n" not in workflow


def test_release_resolves_a_published_scanned_image_and_deploys_by_digest() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "actions/create-github-app-token@" not in workflow
    assert "docker build" not in workflow
    assert "docker push" not in workflow
    assert "ecr:GetAuthorizationToken" not in workflow
    assert "imageTag=${IMAGE_SOURCE_SHA}" in workflow
    assert "image_digest" in workflow
    assert "describe-image-scan-findings" in workflow
    assert "ecr_image.py digest" in workflow
    assert "ecr_image.py scan" in workflow
    assert "--purpose deployment" in workflow
    assert "cloud_one_environment.py validate" in workflow
    assert "runtime" in workflow
    assert "cbiit dev network" not in workflow
    assert workflow.index("\n  plan:\n") < workflow.index("Require the completed VPC contract")
    assert "steps.image.outputs.image_uri" in workflow
    assert "Verify VPC and subnet ownership" in workflow
    assert "cloud_one_environment.py verify-subnets" in workflow
    assert "MapPublicIpOnLaunch" not in workflow


def test_release_rollbacks_use_reviewed_application_history_and_current_infrastructure() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "image_source_sha:" in workflow
    assert "fetch-depth: 0" in workflow
    assert "resolve_release_source.py" in workflow
    assert "ref: ${{ needs.preflight.outputs.image_source_sha }}" not in workflow
    assert "IMAGE_SOURCE_SHA: ${{ needs.preflight.outputs.image_source_sha }}" in workflow
    assert 'test "${infrastructure_source_sha}" = "${GITHUB_SHA}"' in workflow
    assert "Application source:" in workflow
    assert "Deployment source:" in workflow


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
    assert "target-in-service" in workflow
    assert "internal_dev_preview_url" in workflow


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
    assert workflow.count("ensure_initialization_safe.py") == 2
    assert workflow.count("tofu -chdir=infra/cloud-one state list") == 2
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
    assert dockerfile.count("dnf install -y --releasever=latest") == 2
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
    assert "github.event_name == 'pull_request'" in workflow
    assert "uses: ./.github/workflows/publish-image.yml" in workflow
    assert (
        "if: ${{ always() && github.event_name == 'push' && "
        "needs.required.result == 'success' }}" in workflow
    )


def test_ci_consolidates_setup_and_exposes_one_stable_required_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    python_setup = PYTHON_SETUP_ACTION.read_text(encoding="utf-8")
    node_setup = NODE_SETUP_ACTION.read_text(encoding="utf-8")

    assert "\n  quality:\n" in workflow
    for retired_job in ("js-check", "test-js", "type-check", "lint", "security"):
        assert f"\n  {retired_job}:\n" not in workflow
    assert workflow.count("uses: ./.github/actions/setup-python-project") == 3
    assert workflow.count("uses: ./.github/actions/setup-node-project") == 2
    assert "\n  required:\n" in workflow
    assert "name: Required CI gate" in workflow
    assert "if: ${{ always() }}" in workflow
    assert "needs: required" in workflow
    assert "HEAD_REPOSITORY" in workflow
    assert "enable-cache: true" in python_setup
    assert "uv sync --frozen --all-extras" in python_setup
    assert "cache: npm" in node_setup
    assert "npm ci" in node_setup


def test_main_publication_is_immutable_scanned_and_restorable() -> None:
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_call:" in workflow
    assert "workflow_dispatch:" in workflow
    assert 'test "${REQUESTED_REF}" = "refs/heads/main"' in workflow
    assert "resolve_release_source.py" in workflow
    assert "ref: ${{ steps.source.outputs.image_source_sha }}" in workflow
    assert "repositories: agentic_harmonization" in workflow
    assert "imageTag=${IMAGE_SOURCE_SHA}" in workflow
    assert "docker run --rm" in workflow
    assert "docker push" in workflow
    assert workflow.index("docker run --rm") < workflow.index("docker push")
    assert "image-scan-complete" in workflow
    assert "ecr_image.py digest" in workflow
    assert "ecr_image.py scan" in workflow
    assert "--purpose publication" in workflow
