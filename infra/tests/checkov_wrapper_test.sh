#!/usr/bin/env bash
set -euo pipefail

repository_root="$(git rev-parse --show-toplevel)"
cd "${repository_root}"

test_directory="$(mktemp -d)"
invalid_suppression_file="infra/.checkov-wrapper-invalid-suppression.tf"
unregistered_root="infra/modules/.checkov-wrapper-unregistered"
cleanup() {
  rm -f "${invalid_suppression_file}" "${unregistered_root}/main.tf"
  rmdir "${unregistered_root}" 2>/dev/null || true
  rm -rf "${test_directory}"
}
trap cleanup EXIT

test ! -e "${invalid_suppression_file}"
test ! -e "${unregistered_root}"

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

hash_failure_bin="${test_directory}/hash-failure-bin"
mkdir -p "${hash_failure_bin}"
cat > "${hash_failure_bin}/sha256sum" <<'EOF'
#!/usr/bin/env bash
exit 2
EOF
chmod +x "${hash_failure_bin}/sha256sum"
if PATH="${hash_failure_bin}:${PATH}" CHECKOV_UV_BIN="${fake_uv}" \
  CHECKOV_ARTIFACT_ROOT="${test_directory}/hash-failure" \
  bash scripts/check-iac-security.sh; then
  echo "Checkov wrapper unexpectedly passed when evidence hashing failed." >&2
  exit 1
fi

cat > "${invalid_suppression_file}" <<'EOF'
resource "aws_s3_bucket" "invalid" {
  # checkov:skip=CKV_AWS_18:reason=;ref=;owner=;review=2000-99-99
}
EOF
if CHECKOV_UV_BIN="${fake_uv}" CHECKOV_ARTIFACT_ROOT="${test_directory}/invalid-suppression" \
  bash scripts/check-iac-security.sh; then
  echo "Checkov wrapper unexpectedly passed empty metadata and an invalid review date." >&2
  exit 1
fi

cat > "${invalid_suppression_file}" <<'EOF'
resource "aws_s3_bucket" "invalid_date" {
  # checkov:skip=CKV_AWS_18:reason=Fixture;ref=CHECKOV_EXCEPTIONS.md;owner=DataChord Engineering;review=2000-99-99
}
EOF
if CHECKOV_UV_BIN="${fake_uv}" CHECKOV_ARTIFACT_ROOT="${test_directory}/invalid-review-date" \
  bash scripts/check-iac-security.sh; then
  echo "Checkov wrapper unexpectedly passed an invalid review date." >&2
  exit 1
fi

cat > "${invalid_suppression_file}" <<'EOF'
resource "aws_s3_bucket" "expired" {
  # checkov:skip=CKV_AWS_18:reason=Fixture;ref=CHECKOV_EXCEPTIONS.md;owner=DataChord Engineering;review=2000-01-01
}
EOF
if CHECKOV_UV_BIN="${fake_uv}" CHECKOV_ARTIFACT_ROOT="${test_directory}/expired-suppression" \
  bash scripts/check-iac-security.sh; then
  echo "Checkov wrapper unexpectedly passed an expired suppression." >&2
  exit 1
fi

cat > "${invalid_suppression_file}" <<'EOF'
resource "aws_s3_bucket" "missing_reference" {
  # checkov:skip=CKV_AWS_18:reason=Fixture;ref=DOES_NOT_EXIST.md;owner=DataChord Engineering;review=2999-01-01
}
EOF
if CHECKOV_UV_BIN="${fake_uv}" CHECKOV_ARTIFACT_ROOT="${test_directory}/missing-reference" \
  bash scripts/check-iac-security.sh; then
  echo "Checkov wrapper unexpectedly passed a suppression with a missing reference." >&2
  exit 1
fi
rm -f "${invalid_suppression_file}"

mkdir -p "${unregistered_root}"
printf '%s\n' 'resource "terraform_data" "fixture" {}' > "${unregistered_root}/main.tf"
git_with_unregistered_root="${test_directory}/git-with-unregistered-root"
mkdir -p "${git_with_unregistered_root}"
real_git="$(command -v git)"
cat > "${git_with_unregistered_root}/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$#" -eq 3 && "$1" = "ls-files" && "$2" = "--" && "$3" = "infra" ]]; then
  "${REAL_GIT}" "$@"
  echo "infra/modules/.checkov-wrapper-unregistered/main.tf"
else
  exec "${REAL_GIT}" "$@"
fi
EOF
chmod +x "${git_with_unregistered_root}/git"
if PATH="${git_with_unregistered_root}:${PATH}" REAL_GIT="${real_git}" \
  CHECKOV_UV_BIN="${fake_uv}" \
  CHECKOV_ARTIFACT_ROOT="${test_directory}/unregistered-root" \
  bash scripts/check-iac-security.sh; then
  echo "Checkov wrapper unexpectedly passed an unregistered committed IaC directory." >&2
  exit 1
fi
