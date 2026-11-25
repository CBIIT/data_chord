from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from infra.scripts.ecr_image import (
    EcrImageError,
    image_digest,
    inspector_scan_state,
    require_clean_inspector_findings,
    require_enhanced_scanning,
    require_inspector_available,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra" / "scripts" / "ecr_image.py"
DIGEST = f"sha256:{'a' * 64}"


def test_image_digest_requires_exactly_one_immutable_digest() -> None:
    assert image_digest({"imageDetails": [{"imageDigest": DIGEST}]}) == DIGEST

    with pytest.raises(EcrImageError, match="exactly one image"):
        image_digest({"imageDetails": []})
    with pytest.raises(EcrImageError, match="immutable image digest"):
        image_digest({"imageDetails": [{"imageDigest": "latest"}]})


def test_completed_inspector_scan_is_ready() -> None:
    resource_id = f"arn:aws:ecr:us-east-1:211125567571:repository/data-chord-dev/{DIGEST}"
    assert (
        inspector_scan_state(
            {
                "coveredResources": [
                    {
                        "resourceId": resource_id,
                        "resourceType": "AWS_ECR_CONTAINER_IMAGE",
                        "scanStatus": {"statusCode": "ACTIVE", "reason": "SUCCESSFUL"},
                        "lastScannedAt": "2026-11-25T17:00:00Z",
                    }
                ]
            },
            resource_id=resource_id,
        )
        == "complete"
    )


@pytest.mark.parametrize("reason", ("PENDING_INITIAL_SCAN", "SCAN_IN_PROGRESS"))
def test_pending_inspector_scan_is_retryable(reason: str) -> None:
    resource_id = f"arn:aws:ecr:us-east-1:211125567571:repository/data-chord-dev/{DIGEST}"
    assert (
        inspector_scan_state(
            {
                "coveredResources": [
                    {
                        "resourceId": resource_id,
                        "resourceType": "AWS_ECR_CONTAINER_IMAGE",
                        "scanStatus": {"statusCode": "ACTIVE", "reason": reason},
                    }
                ]
            },
            resource_id=resource_id,
        )
        == "pending"
    )


def test_missing_inspector_image_is_retryable() -> None:
    assert inspector_scan_state({"coveredResources": []}, resource_id="repo/image") == "pending"


def test_terminal_inspector_scan_failure_is_rejected() -> None:
    resource_id = f"arn:aws:ecr:us-east-1:211125567571:repository/data-chord-dev/{DIGEST}"
    with pytest.raises(EcrImageError, match="cannot scan.*INACTIVE/UNSUPPORTED_OS"):
        inspector_scan_state(
            {
                "coveredResources": [
                    {
                        "resourceId": resource_id,
                        "resourceType": "AWS_ECR_CONTAINER_IMAGE",
                        "scanStatus": {"statusCode": "INACTIVE", "reason": "UNSUPPORTED_OS"},
                    }
                ]
            },
            resource_id=resource_id,
        )


def test_clean_inspector_findings_are_deployable() -> None:
    require_clean_inspector_findings(
        {
            "findings": [
                {"status": "ACTIVE", "severity": "MEDIUM"},
                {"status": "CLOSED", "severity": "HIGH"},
                {"status": "SUPPRESSED", "severity": "CRITICAL"},
            ]
        },
        purpose="deployment",
    )


def test_active_critical_or_high_findings_block_the_named_operation() -> None:
    with pytest.raises(EcrImageError, match="blocks publication.*CRITICAL.*HIGH"):
        require_clean_inspector_findings(
            {
                "findings": [
                    {"status": "ACTIVE", "severity": "CRITICAL"},
                    {"status": "ACTIVE", "severity": "HIGH"},
                    {"status": "ACTIVE", "severity": "HIGH"},
                ]
            },
            purpose="publication",
        )


def test_registry_requires_continuous_enhanced_scanning_for_repository() -> None:
    require_enhanced_scanning(
        {
            "registryId": "211125567571",
            "scanningConfiguration": {
                "scanType": "ENHANCED",
                "rules": [
                    {
                        "scanFrequency": "CONTINUOUS_SCAN",
                        "repositoryFilters": [
                            {"filter": "data-chord-*", "filterType": "WILDCARD"}
                        ],
                    }
                ],
            },
        },
        repository="data-chord-dev",
    )

    with pytest.raises(EcrImageError, match="continuous scanning does not cover"):
        require_enhanced_scanning(
            {
                "registryId": "211125567571",
                "scanningConfiguration": {
                    "scanType": "ENHANCED",
                    "rules": [
                        {
                            "scanFrequency": "SCAN_ON_PUSH",
                            "repositoryFilters": [
                                {"filter": "data-chord-*", "filterType": "WILDCARD"}
                            ],
                        }
                    ],
                },
            },
            repository="data-chord-dev",
        )


def test_registry_rejects_a_response_without_configuration_settings() -> None:
    with pytest.raises(EcrImageError, match="configuration settings must be a JSON object"):
        require_enhanced_scanning(
            {"registryId": "211125567571"},
            repository="data-chord-dev",
        )


def test_inspector_coverage_api_must_be_available() -> None:
    require_inspector_available({"coveredResources": []})

    with pytest.raises(EcrImageError, match="coverage is unavailable"):
        require_inspector_available({})


def test_cli_prints_the_validated_digest(tmp_path: Path) -> None:
    response = tmp_path / "image.json"
    response.write_text(json.dumps({"imageDetails": [{"imageDigest": DIGEST}]}), encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "digest", str(response)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == DIGEST
