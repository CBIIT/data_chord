#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

targets=(src/ backend/ scripts/ infra/scripts/)
if (( $# > 0 )); then
  targets=("$@")
fi

exec tools/bandit/.venv/bin/bandit \
  -r "${targets[@]}" \
  -c pyproject.toml \
  --severity-level medium \
  --confidence-level medium
