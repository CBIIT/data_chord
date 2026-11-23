#!/usr/bin/env python3
"""Validate and summarize governed Checkov suppressions."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ANNOTATION_MARKER = "checkov:skip="
REQUIRED_FIELDS = {"reason", "ref", "owner", "review"}


@dataclass(frozen=True)
class Suppression:
    source_path: str
    source_line: int
    policy: str
    reason: str
    reference: str
    owner: str
    review: date


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    return parser.parse_args()


def parse_fields(metadata: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in metadata.split(";"):
        key, field_separator, value = item.partition("=")
        key = key.strip()
        value = value.strip()
        if not field_separator or not key:
            raise ValueError(f"malformed metadata field: {item!r}")
        if key in fields:
            raise ValueError(f"duplicate metadata field: {key}")
        fields[key] = value

    missing = REQUIRED_FIELDS - fields.keys()
    unknown = fields.keys() - REQUIRED_FIELDS
    if missing:
        raise ValueError(f"missing metadata fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"unknown metadata fields: {', '.join(sorted(unknown))}")
    empty = sorted(key for key in REQUIRED_FIELDS if not fields[key])
    if empty:
        raise ValueError(f"empty metadata fields: {', '.join(empty)}")
    return fields


def parse_review_date(value: str, today: date) -> date:
    try:
        review_date = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("review must be a real ISO date in YYYY-MM-DD form") from error
    if review_date < today:
        raise ValueError(f"suppression review expired on {review_date.isoformat()}")
    return review_date


def validate_reference(value: str, repository_root: Path) -> None:
    reference_path = (repository_root / value).resolve()
    try:
        reference_path.relative_to(repository_root)
    except ValueError as error:
        raise ValueError("reference must remain inside the repository") from error
    if not reference_path.is_file():
        raise ValueError(f"reference file does not exist: {value}")


def parse_suppression(
    source_path: str,
    source_line: int,
    raw_line: str,
    repository_root: Path,
    today: date,
) -> Suppression:
    _, marker, annotation = raw_line.partition(ANNOTATION_MARKER)
    if not marker:
        raise ValueError(f"suppression is missing {ANNOTATION_MARKER}")

    policy, separator, metadata = annotation.strip().partition(":")
    if not separator or not policy.strip():
        raise ValueError("suppression must include a policy followed by metadata")

    fields = parse_fields(metadata)
    review_date = parse_review_date(fields["review"], today)
    validate_reference(fields["ref"], repository_root)

    return Suppression(
        source_path=source_path,
        source_line=source_line,
        policy=policy.strip(),
        reason=fields["reason"],
        reference=fields["ref"],
        owner=fields["owner"],
        review=review_date,
    )


def main() -> int:
    arguments = parse_arguments()
    repository_root = arguments.repository_root.resolve()
    failures: list[str] = []
    suppressions: list[Suppression] = []

    infrastructure_root = repository_root / "infra"
    if not infrastructure_root.is_dir():
        print("::error::Infrastructure directory does not exist: infra", file=sys.stderr)
        return 1

    for source_file in sorted(infrastructure_root.rglob("*.tf")):
        source_path = source_file.relative_to(repository_root).as_posix()
        for source_line, raw_line in enumerate(
            source_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if ANNOTATION_MARKER not in raw_line:
                continue
            try:
                suppressions.append(
                    parse_suppression(
                        source_path,
                        source_line,
                        raw_line,
                        repository_root,
                        date.today(),
                    )
                )
            except ValueError as error:
                failures.append(f"{source_path}:{source_line}: {error}")

    if failures:
        for failure in failures:
            print(f"::error::{failure}", file=sys.stderr)
        return 1

    for suppression in suppressions:
        print(
            f"- `{suppression.source_path}:{suppression.source_line}` — "
            f"`{suppression.policy}`; owner: {suppression.owner}; "
            f"review: {suppression.review.isoformat()}; "
            f"reference: `{suppression.reference}`"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
