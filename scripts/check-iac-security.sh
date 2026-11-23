#!/usr/bin/env bash
set -uo pipefail

repository_root="$(git rev-parse --show-toplevel)"
cd "${repository_root}"

tool_project="tools/checkov"
roots_file="${tool_project}/roots.txt"
artifact_root="${CHECKOV_ARTIFACT_ROOT:-.artifacts/checkov}"
config_file=".checkov.yml"
uv_bin="${CHECKOV_UV_BIN:-uv}"

die() {
  echo "::error::$*" >&2
  exit 1
}

for required in "${tool_project}/pyproject.toml" "${tool_project}/uv.lock" "${roots_file}" "${config_file}"; do
  test -f "${required}" || die "Required Checkov file is missing: ${required}"
done

command -v "${uv_bin}" >/dev/null 2>&1 || die "uv is required to run the locked Checkov tool environment."

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

manifest_directories="${tmp_dir}/manifest-directories.txt"
discovered_directories="${tmp_dir}/discovered-directories.txt"

awk -F '|' '!/^#/ && NF >= 2 { print $2 }' "${roots_file}" | sort -u > "${manifest_directories}"
find infra -name .terraform.lock.hcl -not -path '*/.terraform/*' -exec dirname {} \; \
  | sort -u > "${discovered_directories}"

if ! diff -u "${manifest_directories}" "${discovered_directories}"; then
  die "The Checkov root manifest does not match the committed OpenTofu roots."
fi

suppression_status=0
while IFS= read -r suppression; do
  if [[ "${suppression}" != *"reason="* ]] ||
     [[ "${suppression}" != *"ref="* ]] ||
     [[ "${suppression}" != *"owner="* ]] ||
     [[ ! "${suppression}" =~ review=[0-9]{4}-[0-9]{2}-[0-9]{2} ]]; then
    echo "::error::Malformed Checkov suppression: ${suppression}" >&2
    echo "Expected reason=...;ref=...;owner=...;review=YYYY-MM-DD" >&2
    suppression_status=1
  fi
  if [[ "${suppression}" =~ ref=([^;]+) ]]; then
    reference="${BASH_REMATCH[1]}"
    if [[ ! -f "${reference}" ]]; then
      echo "::error::Checkov suppression references a missing file: ${reference}" >&2
      suppression_status=1
    fi
  fi
done < <(rg -n 'checkov:skip=' infra -g '*.tf' || true)

if [[ "${suppression_status}" -ne 0 ]]; then
  exit "${suppression_status}"
fi

rm -rf "${artifact_root}"
mkdir -p "${artifact_root}"

checkov_version="$("${uv_bin}" run --project "${tool_project}" --frozen checkov --version)" || \
  die "Unable to run the locked Checkov tool."
printf '%s\n' "${checkov_version}" > "${artifact_root}/version.txt"
git rev-parse HEAD > "${artifact_root}/source-sha.txt"
sha256sum "${config_file}" "${roots_file}" "${tool_project}/uv.lock" \
  > "${artifact_root}/configuration-sha256.txt"

overall_status=0
summary_file="${artifact_root}/summary.md"
{
  echo "## Checkov infrastructure scan"
  echo
  echo "- **Source:** \`$(git rev-parse HEAD)\`"
  echo "- **Version:** \`${checkov_version}\`"
  echo
  echo "| Root | Result | Passed | Failed | Skipped |"
  echo "| --- | --- | ---: | ---: | ---: |"
} > "${summary_file}"

while IFS='|' read -r name directory skip_paths; do
  [[ -z "${name}" || "${name}" == \#* ]] && continue
  test -d "${directory}" || die "Configured Checkov root does not exist: ${directory}"

  output_directory="${artifact_root}/${name}"
  mkdir -p "${output_directory}"

  command=(
    "${uv_bin}" run --project "${tool_project}" --frozen checkov
    --config-file "${config_file}"
    --directory "${directory}"
    --output cli
    --output json
    --output sarif
    --output-file-path "console,${output_directory}/results.json,${output_directory}/results.sarif"
  )
  if [[ -n "${skip_paths}" ]]; then
    IFS=',' read -r -a configured_skip_paths <<< "${skip_paths}"
    for skip_path in "${configured_skip_paths[@]}"; do
      command+=(--skip-path "${skip_path}")
    done
  fi

  echo "Scanning ${name} (${directory})"
  if "${command[@]}"; then
    result="PASS"
  else
    result="FAIL"
    overall_status=1
  fi

  for report in results.json results.sarif; do
    if [[ ! -s "${output_directory}/${report}" ]]; then
      echo "::error::Checkov did not create ${output_directory}/${report}" >&2
      result="ERROR"
      overall_status=1
    fi
  done

  passed="n/a"
  failed="n/a"
  skipped="n/a"
  if [[ -s "${output_directory}/results.json" ]]; then
    read -r passed failed skipped < <(
      python3 - "${output_directory}/results.json" <<'PY'
import json
import sys

try:
    summary = json.load(open(sys.argv[1], encoding="utf-8")).get("summary", {})
    print(summary.get("passed", "n/a"), summary.get("failed", "n/a"), summary.get("skipped", "n/a"))
except (OSError, ValueError, AttributeError):
    print("n/a n/a n/a")
PY
    )
  fi
  echo "| \`${directory}\` | ${result} | ${passed} | ${failed} | ${skipped} |" >> "${summary_file}"
done < "${roots_file}"

{
  echo
  echo "### Active suppressions"
  echo
  if rg -n 'checkov:skip=' infra -g '*.tf' > "${tmp_dir}/suppressions.txt"; then
    sed 's/^/- `/' "${tmp_dir}/suppressions.txt" | sed 's/$/`/'
  else
    echo "None."
  fi
} >> "${summary_file}"

cat "${summary_file}"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  cat "${summary_file}" >> "${GITHUB_STEP_SUMMARY}"
fi

exit "${overall_status}"
