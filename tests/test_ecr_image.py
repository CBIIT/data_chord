from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from infra.scripts.ecr_image import EcrImageError, image_digest, require_clean_scan

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra" / "scripts" / "ecr_image.py"
DIGEST = f"sha256:{'a' * 64}"


def test_image_digest_requires_exactly_one_immutable_digest() -> None:
    assert image_digest({"imageDetails": [{"imageDigest": DIGEST}]}) == DIGEST

    with pytest.raises(EcrImageError, match="exactly one image"):
        image_digest({"imageDetails": []})
    with pytest.raises(EcrImageError, match="immutable image digest"):
        image_digest({"imageDetails": [{"imageDigest": "latest"}]})


def test_clean_completed_scan_is_deployable() -> None:
    require_clean_scan(
        {
            "imageScanStatus": {"status": "COMPLETE"},
            "imageScanFindings": {"findingSeverityCounts": {"MEDIUM": 4}},
        },
        purpose="deployment",
    )


@pytest.mark.parametrize("status", (None, "IN_PROGRESS", "FAILED"))
def test_incomplete_scan_is_rejected(status: str | None) -> None:
    with pytest.raises(EcrImageError, match="scan is not complete"):
        require_clean_scan(
            {
                "imageScanStatus": {"status": status},
                "imageScanFindings": {"findingSeverityCounts": {}},
            },
            purpose="deployment",
        )


def test_critical_or_high_findings_block_the_named_operation() -> None:
    with pytest.raises(EcrImageError, match="blocks publication.*CRITICAL.*HIGH"):
        require_clean_scan(
            {
                "imageScanStatus": {"status": "COMPLETE"},
                "imageScanFindings": {
                    "findingSeverityCounts": {"CRITICAL": 1, "HIGH": 2},
                },
            },
            purpose="publication",
        )


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
