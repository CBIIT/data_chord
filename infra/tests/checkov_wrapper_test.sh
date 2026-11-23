#!/usr/bin/env bash
set -euo pipefail

repository_root="$(git rev-parse --show-toplevel)"
cd "${repository_root}"

test_directory="$(mktemp -d)"
trap 'rm -rf "${test_directory}"' EXIT

fake_uv="${test_directory}/uv"
cat > "${fake_uv}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ " $* " == *" checkov --version "* ]]; then
  echo "Checkov, version 3.4.6"
  exit 0
fi

directory=""
output_paths=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --directory)
      directory="$2"
      shift 2
      ;;
    --output-file-path)
      output_paths="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

IFS=',' read -r console json_path sarif_path <<< "${output_paths}"
test "${console}" = "console"
mkdir -p "$(dirname "${json_path}")" "$(dirname "${sarif_path}")"
printf '{"summary":{"passed":1,"failed":0,"skipped":0}}\n' > "${json_path}"
if [[ -z "${FAKE_CHECKOV_OMIT_SARIF_ROOT:-}" || "${directory}" != "${FAKE_CHECKOV_OMIT_SARIF_ROOT}" ]]; then
  printf '{"version":"2.1.0","runs":[]}\n' > "${sarif_path}"
fi

if [[ -n "${FAKE_CHECKOV_FAIL_ROOT:-}" && "${directory}" = "${FAKE_CHECKOV_FAIL_ROOT}" ]]; then
  exit 1
fi
EOF
chmod +x "${fake_uv}"

success_artifacts="${test_directory}/success"
CHECKOV_UV_BIN="${fake_uv}" CHECKOV_ARTIFACT_ROOT="${success_artifacts}" \
  bash scripts/check-iac-security.sh

for root in full-application cloud-one customer-platform shared-data-plane; do
  test -s "${success_artifacts}/${root}/results.json"
  test -s "${success_artifacts}/${root}/results.sarif"
done

failure_artifacts="${test_directory}/failure"
if CHECKOV_UV_BIN="${fake_uv}" CHECKOV_ARTIFACT_ROOT="${failure_artifacts}" \
  FAKE_CHECKOV_FAIL_ROOT="infra/cloud-one" bash scripts/check-iac-security.sh; then
  echo "Checkov wrapper unexpectedly passed a failing root." >&2
  exit 1
fi

grep -q '| `infra/cloud-one` | FAIL | 1 | 0 | 0 |' "${failure_artifacts}/summary.md"
test -s "${failure_artifacts}/shared-data-plane/results.json"
test -s "${failure_artifacts}/shared-data-plane/results.sarif"

missing_report_artifacts="${test_directory}/missing-report"
if CHECKOV_UV_BIN="${fake_uv}" CHECKOV_ARTIFACT_ROOT="${missing_report_artifacts}" \
  FAKE_CHECKOV_OMIT_SARIF_ROOT="infra/customer-platform" bash scripts/check-iac-security.sh; then
  echo "Checkov wrapper unexpectedly passed with a missing SARIF report." >&2
  exit 1
fi

grep -q '| `infra/customer-platform` | ERROR | 1 | 0 | 0 |' \
  "${missing_report_artifacts}/summary.md"
test -s "${missing_report_artifacts}/shared-data-plane/results.sarif"
