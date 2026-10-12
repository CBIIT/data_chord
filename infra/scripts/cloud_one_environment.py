#!/usr/bin/env python3
"""Validate and render one checked-in Cloud One deployment environment."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_FIELDS = {
    "account_id",
    "application_role_boundary_arn",
    "application_role_path",
    "ingress_cidr_blocks",
    "private_subnet_ids",
    "region",
    "schema_version",
    "state_bucket_name",
    "vpc_id",
}
_ACCOUNT = re.compile(r"^[0-9]{12}$")
_REGION = re.compile(r"^[a-z]{2}(?:-[a-z]+)+-[0-9]$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_SLUG = re.compile(r"^[a-z][a-z0-9-]*$")
_VPC = re.compile(r"^vpc-[0-9a-f]+$")
_SUBNET = re.compile(r"^subnet-[0-9a-f]+$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_STAGES = {"dev", "qa", "staging", "prod"}


class ConfigurationError(ValueError):
    """The Cloud One environment is incomplete, unsafe, or malformed."""


@dataclass(frozen=True)
class Environment:
    account_id: str
    application_role_boundary_arn: str
    application_role_path: str
    ingress_cidr_blocks: tuple[str, ...]
    private_subnet_ids: tuple[str, ...]
    region: str
    state_bucket_name: str
    vpc_id: str | None
    target: str
    stage: str

    @property
    def state_key(self) -> str:
        return f"datachord/{self.target}/{self.stage}/cloud-one/tofu.tfstate"

    def tofu_variables(self, *, runtime_enabled: bool, image_digest: str | None) -> dict[str, object]:
        return {
            "application_role_boundary_arn": self.application_role_boundary_arn,
            "application_role_path": self.application_role_path,
            "aws_region": self.region,
            "deployment_target": self.target,
            "environment": self.stage,
            "expected_account_id": self.account_id,
            "image_digest": image_digest,
            "ingress_cidr_blocks": list(self.ingress_cidr_blocks),
            "private_subnet_ids": list(self.private_subnet_ids),
            "runtime_enabled": runtime_enabled,
            "vpc_id": self.vpc_id,
        }


def load(path: Path, target: str, stage: str) -> Environment:
    if not _SLUG.fullmatch(target):
        raise ConfigurationError("target must be a lowercase slug")
    if stage not in _STAGES:
        raise ConfigurationError("stage must be dev, qa, staging, or prod")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"environment does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"environment is unreadable: {path}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError("environment must contain one JSON object")
    document = {str(key): value for key, value in raw.items()}
    _require_fields(document)
    if document.get("schema_version") != 1:
        raise ConfigurationError("schema_version must be 1")
    environment = Environment(
        account_id=_string(document, "account_id"),
        application_role_boundary_arn=_string(document, "application_role_boundary_arn"),
        application_role_path=_string(document, "application_role_path"),
        ingress_cidr_blocks=_strings(document, "ingress_cidr_blocks"),
        private_subnet_ids=_strings(document, "private_subnet_ids"),
        region=_string(document, "region"),
        state_bucket_name=_string(document, "state_bucket_name"),
        vpc_id=_optional_string(document, "vpc_id"),
        target=target,
        stage=stage,
    )
    _validate(environment)
    return environment


def _validate(environment: Environment) -> None:
    if not _ACCOUNT.fullmatch(environment.account_id):
        raise ConfigurationError("account_id must be a 12-digit AWS account id")
    if not _REGION.fullmatch(environment.region):
        raise ConfigurationError("region is invalid")
    if not _BUCKET.fullmatch(environment.state_bucket_name):
        raise ConfigurationError("state_bucket_name is invalid")
    boundary_prefix = f"arn:aws:iam::{environment.account_id}:policy/"
    if not environment.application_role_boundary_arn.startswith(boundary_prefix):
        raise ConfigurationError("application_role_boundary_arn must be in account_id")
    if environment.application_role_path != "/application/":
        raise ConfigurationError("application_role_path must be /application/")
    if environment.vpc_id is not None and not _VPC.fullmatch(environment.vpc_id):
        raise ConfigurationError("vpc_id must be null or an AWS VPC id")
    invalid_subnets = [value for value in environment.private_subnet_ids if not _SUBNET.fullmatch(value)]
    if invalid_subnets:
        raise ConfigurationError(f"invalid private subnet id: {invalid_subnets[0]}")
    if len(set(environment.private_subnet_ids)) != len(environment.private_subnet_ids):
        raise ConfigurationError("private_subnet_ids must not contain duplicates")


def require_runtime(environment: Environment, digest: str) -> None:
    if not _DIGEST.fullmatch(digest):
        raise ConfigurationError("runtime image digest must be sha256 followed by 64 lowercase hex characters")
    if environment.vpc_id is None:
        raise ConfigurationError("runtime deployment is blocked until vpc_id is populated from the VPC ticket")
    if len(environment.private_subnet_ids) < 2:
        raise ConfigurationError("runtime deployment requires at least two private_subnet_ids")


def _require_fields(document: dict[str, object]) -> None:
    extra = sorted(set(document) - _FIELDS)
    missing = sorted(_FIELDS - set(document))
    if extra or missing:
        details = []
        if extra:
            details.append(f"unsupported fields: {', '.join(extra)}")
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        raise ConfigurationError("; ".join(details))


def _string(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{key} must be a non-empty string")
    return value


def _optional_string(document: dict[str, object], key: str) -> str | None:
    value = document.get(key)
    if value is not None and (not isinstance(value, str) or not value):
        raise ConfigurationError(f"{key} must be null or a non-empty string")
    return value


def _strings(document: dict[str, object], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(f"{key} must be a list of strings")
    return tuple(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("validate", "get", "tofu-vars"))
    parser.add_argument("path", type=Path)
    parser.add_argument("target")
    parser.add_argument("stage")
    parser.add_argument("value", nargs="?")
    parser.add_argument("image_digest", nargs="?")
    return parser


def main(arguments: list[str]) -> int:
    try:
        args = _parser().parse_args(arguments)
        environment = load(args.path, args.target, args.stage)
        if args.action == "validate":
            if args.value == "runtime":
                require_runtime(environment, args.image_digest or "")
            elif args.value not in (None, "bootstrap") or args.image_digest is not None:
                raise ConfigurationError("validate accepts only bootstrap or runtime IMAGE_DIGEST")
            return 0
        if args.action == "get":
            if args.image_digest is not None:
                raise ConfigurationError("get accepts exactly one field")
            values = {
                "account_id": environment.account_id,
                "region": environment.region,
                "state_bucket_name": environment.state_bucket_name,
                "state_key": environment.state_key,
            }
            if args.value not in values:
                raise ConfigurationError(f"unknown environment field: {args.value}")
            print(values[args.value])
            return 0
        if args.value == "bootstrap" and args.image_digest is None:
            variables = environment.tofu_variables(runtime_enabled=False, image_digest=None)
        elif args.value == "runtime" and args.image_digest is not None:
            require_runtime(environment, args.image_digest)
            variables = environment.tofu_variables(runtime_enabled=True, image_digest=args.image_digest)
        else:
            raise ConfigurationError("tofu-vars requires bootstrap or runtime IMAGE_DIGEST")
        print(json.dumps(variables, separators=(",", ":"), sort_keys=True))
        return 0
    except ConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
