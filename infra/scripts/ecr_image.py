#!/usr/bin/env python3
"""Validate the immutable ECR image metadata used by Cloud One releases."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_BLOCKING_SEVERITIES = ("CRITICAL", "HIGH")
_PENDING_SCAN_REASONS = ("PENDING_INITIAL_SCAN", "SCAN_IN_PROGRESS")
_FINDING_STATUSES = ("ACTIVE", "CLOSED", "SUPPRESSED")


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


def inspector_scan_state(document: object, *, resource_id: str) -> str:
    """Return whether Inspector has completed the initial scan for one ECR image."""

    root = _object(document, "Amazon Inspector coverage response")
    resources = root.get("coveredResources")
    if not isinstance(resources, list):
        raise EcrImageError("Amazon Inspector coverage is unavailable")
    if not resources:
        return "pending"

    completed = False
    pending = False
    for raw_resource in resources:
        resource = _object(raw_resource, "Amazon Inspector covered resource")
        if resource.get("resourceId") != resource_id:
            raise EcrImageError("Amazon Inspector returned coverage for an unexpected image")
        if resource.get("resourceType") != "AWS_ECR_CONTAINER_IMAGE":
            raise EcrImageError("Amazon Inspector returned an unexpected resource type")
        status = _object(resource.get("scanStatus"), "Amazon Inspector scan status")
        status_code = status.get("statusCode")
        reason = status.get("reason")
        if status_code == "ACTIVE" and reason == "SUCCESSFUL":
            last_scanned_at = resource.get("lastScannedAt")
            if not isinstance(last_scanned_at, str) or not last_scanned_at:
                raise EcrImageError("Amazon Inspector omitted the completed scan timestamp")
            completed = True
        elif reason in _PENDING_SCAN_REASONS:
            pending = True
        else:
            raise EcrImageError(
                f"Amazon Inspector cannot scan the image: "
                f"{status_code or 'UNKNOWN'}/{reason or 'UNKNOWN'}"
            )
    if completed and not pending:
        return "complete"
    return "pending"


def require_clean_inspector_findings(document: object, *, purpose: str) -> None:
    """Require no active critical or high Inspector findings for one ECR image."""

    root = _object(document, "Amazon Inspector findings response")
    findings = root.get("findings")
    if not isinstance(findings, list):
        raise EcrImageError("Amazon Inspector findings are unavailable")
    blocked = dict.fromkeys(_BLOCKING_SEVERITIES, 0)
    for raw_finding in findings:
        finding = _object(raw_finding, "Amazon Inspector finding")
        status = finding.get("status")
        if status not in _FINDING_STATUSES:
            raise EcrImageError("Amazon Inspector returned an invalid finding status")
        severity = finding.get("severity")
        if not isinstance(severity, str):
            raise EcrImageError("Amazon Inspector returned an invalid finding severity")
        if status == "ACTIVE" and severity in blocked:
            blocked[severity] += 1
    if sum(blocked.values()):
        raise EcrImageError(f"Amazon Inspector blocks {purpose}: {blocked}")


def require_enhanced_scanning(document: object, *, repository: str) -> None:
    """Require continuous Amazon Inspector scanning for the image repository."""

    root = _object(document, "ECR registry scanning configuration")
    configuration = _object(
        root.get("scanningConfiguration"),
        "ECR registry scanning configuration settings",
    )
    if configuration.get("scanType") != "ENHANCED":
        raise EcrImageError("ECR enhanced scanning is unavailable")
    rules = configuration.get("rules")
    if not isinstance(rules, list):
        raise EcrImageError("ECR registry scanning rules must be a list")
    for raw_rule in rules:
        rule = _object(raw_rule, "ECR registry scanning rule")
        if rule.get("scanFrequency") != "CONTINUOUS_SCAN":
            continue
        filters = rule.get("repositoryFilters")
        if not isinstance(filters, list):
            raise EcrImageError("ECR repository filters must be a list")
        for raw_filter in filters:
            repository_filter = _object(raw_filter, "ECR repository filter")
            pattern = repository_filter.get("filter")
            if repository_filter.get("filterType") == "WILDCARD" and isinstance(pattern, str):
                if fnmatch.fnmatchcase(repository, pattern):
                    return
    raise EcrImageError(f"Amazon Inspector continuous scanning does not cover {repository}")


def require_inspector_available(document: object) -> None:
    """Require a well-formed response from the Amazon Inspector coverage API."""

    root = _object(document, "Amazon Inspector coverage response")
    resources = root.get("coveredResources")
    if not isinstance(resources, list):
        raise EcrImageError("Amazon Inspector coverage is unavailable")


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
    coverage = subparsers.add_parser("coverage")
    coverage.add_argument("response", type=Path)
    coverage.add_argument("--resource-id", required=True)
    findings = subparsers.add_parser("findings")
    findings.add_argument("response", type=Path)
    findings.add_argument("--purpose", choices=("deployment", "publication"), required=True)
    registry = subparsers.add_parser("registry")
    registry.add_argument("response", type=Path)
    registry.add_argument("--repository", required=True)
    inspector = subparsers.add_parser("inspector")
    inspector.add_argument("response", type=Path)
    return parser


def main(arguments: list[str]) -> int:
    try:
        args = _parser().parse_args(arguments)
        document = _load(args.response)
        if args.action == "digest":
            print(image_digest(document))
        elif args.action == "coverage":
            print(inspector_scan_state(document, resource_id=args.resource_id))
        elif args.action == "findings":
            require_clean_inspector_findings(document, purpose=args.purpose)
        elif args.action == "registry":
            require_enhanced_scanning(document, repository=args.repository)
        else:
            require_inspector_available(document)
        return 0
    except EcrImageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
