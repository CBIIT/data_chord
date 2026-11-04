#!/usr/bin/env python3
"""Validate the immutable ECR image metadata used by Cloud One releases."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_BLOCKING_SEVERITIES = ("CRITICAL", "HIGH")


class EcrImageError(ValueError):
    """ECR metadata does not identify a deployable image."""


def image_digest(document: object) -> str:
    """Return the one immutable digest in an ECR describe-images response."""

    root = _object(document, "ECR image response")
    details = root.get("imageDetails")
    if not isinstance(details, list) or len(details) != 1:
        raise EcrImageError("ECR did not return exactly one image")
    detail = _object(details[0], "ECR image detail")
    digest = detail.get("imageDigest")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise EcrImageError("ECR did not return one immutable image digest")
    return digest


def require_clean_scan(document: object, *, purpose: str) -> None:
    """Require a completed ECR scan with no critical or high findings."""

    root = _object(document, "ECR scan response")
    scan_status = _object(root.get("imageScanStatus"), "ECR image scan status")
    status = scan_status.get("status")
    if status != "COMPLETE":
        label = status if isinstance(status, str) and status else "UNKNOWN"
        raise EcrImageError(f"ECR scan is not complete: {label}")

    findings = _object(root.get("imageScanFindings"), "ECR image scan findings")
    raw_counts = _object(findings.get("findingSeverityCounts", {}), "ECR finding severity counts")
    blocked: dict[str, int] = {}
    for level in _BLOCKING_SEVERITIES:
        value = raw_counts.get(level, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise EcrImageError(f"ECR returned an invalid {level} finding count")
        blocked[level] = value
    if sum(blocked.values()):
        raise EcrImageError(f"ECR scan blocks {purpose}: {blocked}")


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EcrImageError(f"{label} must be a JSON object")
    return {str(key): item for key, item in value.items()}


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EcrImageError(f"ECR response does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EcrImageError(f"ECR response is unreadable: {path}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    digest = subparsers.add_parser("digest")
    digest.add_argument("response", type=Path)
    scan = subparsers.add_parser("scan")
    scan.add_argument("response", type=Path)
    scan.add_argument("--purpose", choices=("deployment", "publication"), required=True)
    return parser


def main(arguments: list[str]) -> int:
    try:
        args = _parser().parse_args(arguments)
        document = _load(args.response)
        if args.action == "digest":
            print(image_digest(document))
        else:
            require_clean_scan(document, purpose=args.purpose)
        return 0
    except EcrImageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
