from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from infra.scripts.ensure_initialization_safe import ensure_safe, runtime_resources

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra" / "scripts" / "ensure_initialization_safe.py"


def test_empty_state_is_safe_for_initialization() -> None:
    ensure_safe("")


def test_prerequisite_only_state_is_safe_for_initialization() -> None:
    ensure_safe(
        "\n".join(
            (
                "aws_ecr_repository.app",
                "aws_ecs_cluster.app",
                "module.data_plane.aws_s3_bucket.workflow",
            )
        )
    )


@pytest.mark.parametrize(
    "address",
    (
        "aws_ecs_service.app[0]",
        "aws_ecs_task_definition.app[0]",
        "aws_security_group.task[0]",
        "aws_lb.internal_dev[0]",
    ),
)
def test_runtime_state_is_rejected(address: str) -> None:
    with pytest.raises(ValueError, match="normal DataChord plan/deploy workflow"):
        ensure_safe(address)


def test_runtime_resource_report_is_sorted_and_ignores_prerequisites() -> None:
    assert runtime_resources(
        "\n".join(
            (
                "aws_security_group.task[0]",
                "aws_ecr_repository.app",
                "aws_ecs_service.app[0]",
            )
        )
    ) == ("aws_ecs_service.app[0]", "aws_security_group.task[0]")


def test_cli_rejects_runtime_state_file(tmp_path: Path) -> None:
    state_list = tmp_path / "state.txt"
    state_list.write_text("aws_ecs_service.app[0]\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), str(state_list)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "application initialization is restricted" in result.stderr
