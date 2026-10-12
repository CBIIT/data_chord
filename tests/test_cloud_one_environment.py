from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra" / "scripts" / "cloud_one_environment.py"


def _document() -> dict[str, object]:
    return {
        "account_id": "211125567571",
        "application_role_boundary_arn": ("arn:aws:iam::211125567571:policy/cbiit-datachord-application-role-boundary"),
        "application_role_path": "/application/",
        "ingress_cidr_blocks": [],
        "private_subnet_ids": [],
        "region": "us-east-1",
        "schema_version": 1,
        "state_bucket_name": "cbiit-datachord-state-211125567571-us-east-1",
        "vpc_id": None,
    }


def _environment(tmp_path: Path, document: dict[str, object] | None = None) -> Path:
    path = tmp_path / "dev.json"
    path.write_text(json.dumps(document or _document()), encoding="utf-8")
    return path


def _run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), *(str(argument) for argument in arguments)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_bootstrap_allows_pending_network_but_runtime_fails_closed(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    digest = "sha256:" + "a" * 64

    bootstrap = _run("tofu-vars", environment, "cbiit", "dev", "bootstrap")
    runtime = _run("tofu-vars", environment, "cbiit", "dev", "runtime", digest)

    assert bootstrap.returncode == 0, bootstrap.stderr
    assert json.loads(bootstrap.stdout)["runtime_enabled"] is False
    assert runtime.returncode == 2
    assert "blocked until vpc_id is populated" in runtime.stderr


def test_runtime_renders_only_after_exact_network_and_digest(tmp_path: Path) -> None:
    document = _document()
    document["vpc_id"] = "vpc-0123456789abcdef0"
    document["private_subnet_ids"] = [
        "subnet-0123456789abcdef0",
        "subnet-0fedcba9876543210",
    ]
    environment = _environment(tmp_path, document)
    digest = "sha256:" + "b" * 64

    result = _run("tofu-vars", environment, "cbiit", "dev", "runtime", digest)

    assert result.returncode == 0, result.stderr
    variables = json.loads(result.stdout)
    assert variables["runtime_enabled"] is True
    assert variables["image_digest"] == digest
    assert variables["expected_account_id"] == "211125567571"
    assert variables["aws_region"] == "us-east-1"


def test_environment_contract_rejects_unknown_fields(tmp_path: Path) -> None:
    document = _document()
    document["role_arn"] = "not-owned-here"

    result = _run("validate", _environment(tmp_path, document), "cbiit", "dev")

    assert result.returncode == 2
    assert "unsupported fields: role_arn" in result.stderr
