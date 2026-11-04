#!/usr/bin/env python3
"""Reject one-time application initialization after runtime creation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_RUNTIME_RESOURCES = {
    "aws_ecs_service.app[0]",
    "aws_ecs_task_definition.app[0]",
    "aws_lb.internal_dev[0]",
    "aws_lb_listener.internal_dev_http[0]",
    "aws_lb_target_group.internal_dev[0]",
    "aws_security_group.internal_alb[0]",
    "aws_security_group.task[0]",
}


def runtime_resources(state_addresses: str) -> tuple[str, ...]:
    """Return runtime resources present in an OpenTofu state listing."""
    addresses = {line.strip() for line in state_addresses.splitlines() if line.strip()}
    return tuple(sorted(addresses & _RUNTIME_RESOURCES))


def ensure_safe(state_addresses: str) -> None:
    """Raise when an established runtime must use the normal release workflow."""
    existing = runtime_resources(state_addresses)
    if existing:
        resources = ", ".join(existing)
        raise ValueError(
            "application initialization is restricted to a new environment; "
            f"runtime state already contains: {resources}. "
            "Use the normal DataChord plan/deploy workflow instead."
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "state_list",
        nargs="?",
        type=Path,
        help="OpenTofu state-list file; omit to read standard input",
    )
    return parser


def main(arguments: list[str]) -> int:
    args = _parser().parse_args(arguments)
    try:
        state_addresses = (
            args.state_list.read_text(encoding="utf-8") if args.state_list is not None else sys.stdin.read()
        )
        ensure_safe(state_addresses)
        return 0
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
