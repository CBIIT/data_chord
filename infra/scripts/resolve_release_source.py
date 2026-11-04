#!/usr/bin/env python3
"""Resolve a reviewed application commit for one Cloud One release."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class ReleaseSourceError(ValueError):
    """The requested application source is not safe to release."""


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ReleaseSourceError("could not inspect the release repository") from exc


def _commit(repository: Path, value: str, field: str) -> str:
    if not _FULL_SHA.fullmatch(value):
        raise ReleaseSourceError(f"{field} must be a full 40-character lowercase Git commit SHA")
    result = _git(repository, "rev-parse", "--verify", f"{value}^{{commit}}")
    if result.returncode != 0:
        raise ReleaseSourceError(f"{field} does not identify a commit in the release repository")
    resolved = result.stdout.strip()
    if resolved != value:
        raise ReleaseSourceError(f"{field} does not identify the expected commit")
    return resolved


def resolve_release_source(repository: Path, current: str, requested: str) -> str:
    """Return current or a reviewed historical commit reachable from current."""

    current_commit = _commit(repository, current, "current deployment source")
    requested_commit = _commit(
        repository,
        requested or current_commit,
        "image_source_sha",
    )
    ancestor = _git(
        repository,
        "merge-base",
        "--is-ancestor",
        requested_commit,
        current_commit,
    )
    if ancestor.returncode == 1:
        raise ReleaseSourceError("image_source_sha must be reachable from the current main commit")
    if ancestor.returncode != 0:
        raise ReleaseSourceError("could not verify image_source_sha ancestry")
    return requested_commit


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--requested", default="")
    return parser


def main(arguments: list[str]) -> int:
    args = _parser().parse_args(arguments)
    try:
        print(resolve_release_source(args.repository, args.current, args.requested))
        return 0
    except ReleaseSourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
