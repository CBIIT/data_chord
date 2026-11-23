# DataChord Checkov Implementation Plan

**Status:** Implemented on `codex/integrate-checkov`; pull-request verification pending

**Owner:** Chris Harman, DataChord engineering

**Target repository:** `CBIIT/data_chord`

**Last updated:** 2026-11-23

This is the working implementation plan for adding Checkov to DataChord. It is intentionally separate from the Cloud One migration tracker. When this work is completed, the migration tracker will be updated with the verified results and its Checkov boxes will be checked off.

## Alignment

### What we are trying to achieve

- Detect unsafe OpenTofu configurations before they merge or reach AWS.
- Scan every DataChord-owned OpenTofu root and shared module with one repeatable policy.
- Give developers one local command that behaves the same way as CI.
- Make Checkov a required pull-request and main-branch gate.
- Retain reviewable evidence showing which source commit and infrastructure roots were scanned.
- Make every accepted exception explicit, narrow, owned, reviewable, and temporary.
- Keep the design simple enough to reuse later in bootstrap and deployment-plan workflows.

### What we are not trying to do

- We are not creating a separate Git repository or hosted Checkov service.
- We are not adding Checkov to the DataChord application runtime or application dependency environment.
- We are not replacing `tofu fmt`, `tofu validate`, `tofu test`, Bandit, dependency auditing, ECR or Inspector scanning, Invicti, Prisma Cloud, or Fast ATO review.
- We are not connecting to Prisma Cloud, uploading findings to an external platform, or introducing a Prisma API key in the first implementation.
- We are not scanning live AWS configuration; this phase scans the version-controlled OpenTofu source.
- We are not expanding the first implementation to GitHub Actions, Dockerfile, secrets, or software-composition scanning. Those can be evaluated separately after the Terraform gate is stable.
- We are not hiding the existing repository behind a permanent broad baseline.
- We are not changing application behavior, AWS resources, or deployment topology merely to install the scanner.

### Success definition

The work is complete when a developer can run one documented local command, CI runs the same locked scanner against all four OpenTofu roots without secrets or AWS access, every non-suppressed failure blocks the required CI gate, results are retained on passing and failing runs, and the migration tracker records the completed integration and any remaining security follow-up.

## Repository placement and ownership

### Where this belongs

The implementation belongs in the existing `CBIIT/data_chord` repository because that repository owns:

- `infra/`, the full DataChord application root;
- `infra/cloud-one/`, the CBIIT Cloud One deployment root;
- `infra/customer-platform/`, the customer-owned runtime root;
- `infra/modules/data-plane/`, the reusable data-plane module; and
- `.github/workflows/ci.yml`, the required CI gate that validates this infrastructure.

It does not belong in `CBIIT/datachord-infrastructure`, which owns the AWS account foundation rather than these application roots. That repository should receive its own Checkov integration later because its policies, roots, findings, and release gate are independently owned. It does not belong in `agentic_harmonization`, which is an application dependency and does not own DataChord infrastructure.

### What a separately locked tool environment means

No new Git repository, service, or AWS environment is created. The existing repository gains a small tool-only Python project:

```text
data_chord/
├── tools/
│   └── checkov/
│       ├── pyproject.toml
│       └── uv.lock
├── scripts/
│   └── check-iac-security.sh
├── .checkov.yml
└── Justfile
```

The tool project has one direct dependency: the exact approved Checkov version. A representative configuration is:

```toml
[project]
name = "datachord-checkov"
version = "0.0.0"
requires-python = ">=3.13,<3.14"
dependencies = [
    "checkov==3.4.6",
]
```

`tools/checkov/uv.lock` locks Checkov's transitive dependencies independently from the application `uv.lock`. Local and CI execution use that tool project explicitly:

```bash
uv sync --project tools/checkov --frozen
uv run --project tools/checkov checkov --version
just checkov
```

This separation matters because:

- Checkov has a large scanner-specific dependency tree that the application does not need.
- Scanner upgrades should not cause unrelated application dependency changes.
- The current application environment includes a private GitHub dependency, but Checkov must run on fork pull requests without private credentials.
- Application dependency auditing should describe the application, not a development scanner that is never shipped.
- The scanner remains reproducible because its complete environment is committed and locked.

The separate environment is still part of the same repository, reviewed in the same pull request, and executed by the same CI workflow.

## Current repository context

- `.github/workflows/ci.yml` already has an `infrastructure` job that runs formatting, initialization, validation, OpenTofu tests, deployment-flow tests, and shell syntax checks.
- The `Required CI gate` already aggregates required jobs, and successful main CI automatically calls the image-publication workflow.
- Infrastructure scanning must not require the GitHub App credential used by the application Python environment.
- Fork pull requests intentionally lack access to private application dependencies, AWS credentials, and repository secrets.
- All Terraform module sources currently used by the four roots are local, so the first Checkov integration does not need to download external modules.
- GitHub Actions and third-party actions in this repository are pinned to immutable commit SHAs; the Checkov toolchain should follow the same reproducibility principle.

## Proposed implementation

### 1. Lock the scanner as a repository tool

Add `tools/checkov/pyproject.toml` and `tools/checkov/uv.lock`.

- Pin Checkov `3.4.6`, the verified current release when this plan was written.
- Use Python 3.13, which is supported by that release and already fits the repository's Python direction.
- Use the repository's existing pinned `astral-sh/setup-uv` action and pinned `uv` version in CI.
- Use `uv sync --project tools/checkov --frozen`; CI must not resolve an uncommitted dependency set.
- Upgrade Checkov in a dedicated dependency pull request that includes the lockfile diff and a clean scan.

### 2. Define deterministic Checkov configuration

Add `.checkov.yml` with repository-wide defaults:

- framework: Terraform only;
- local open-source mode;
- no Prisma API key;
- no result upload;
- `--skip-download` behavior so policy metadata is not fetched from the platform;
- compact, readable console output;
- generated directories such as `.terraform/` excluded; and
- no broad baseline file.

Output paths remain script arguments because each root needs its own JSON and SARIF files.

### 3. Maintain an explicit root manifest

Add `tools/checkov/roots.txt` or an equivalently simple manifest containing:

```text
infra
infra/cloud-one
infra/customer-platform
infra/modules/data-plane
```

The main `infra/` invocation must exclude its nested roots so graph policies do not combine independent deployments or report the same resources multiple times. The other three roots are scanned independently.

The wrapper must also discover directories containing root-level `.tf` or `.tftest.hcl` files and fail if an expected infrastructure root is absent from the manifest. Adding a new root must therefore include an explicit policy decision rather than silently escaping scanning.

### 4. Add one local and CI wrapper

Add `scripts/check-iac-security.sh` as the only supported Checkov entry point.

The wrapper will:

1. verify it is running from the repository root;
2. verify the locked Checkov version;
3. read the explicit root manifest;
4. create a clean `.artifacts/checkov/` output directory;
5. scan every root independently with Terraform-only and no-download settings;
6. write human-readable output to the console;
7. write JSON and SARIF beneath `.artifacts/checkov/<root-name>/`;
8. continue through every root even if an earlier root fails, so the run produces a complete finding set;
9. print a final per-root summary and active suppression list; and
10. exit nonzero if any root has a non-suppressed failure, a scanner error, a missing report, or an uncovered root.

Add `just checkov` as a short developer command that invokes this wrapper. Developers should not need to remember raw Checkov arguments.

### 5. Add a distinct CI job in the existing workflow

Add one `iac-security` job to `.github/workflows/ci.yml`; do not create another workflow.

The job will:

1. check out the repository;
2. install the repository's pinned `uv` version;
3. install Python 3.13;
4. synchronize only `tools/checkov` with `--frozen`;
5. run `scripts/check-iac-security.sh`;
6. upload `.artifacts/checkov/` with `if: always()` and an initial 14-day retention; and
7. write a job summary showing each root, result, finding count, and suppression count.

The job needs only `contents: read`. It receives no AWS credentials, GitHub App key, Prisma key, or private dependency token. It must therefore run identically for internal and fork pull requests.

Update the existing `required` job to:

- include `iac-security` in `needs`;
- require `IAC_SECURITY_RESULT=success`; and
- preserve the existing special handling for jobs that are intentionally skipped on fork pull requests.

The existing main-branch image publication already waits on the required gate, so a Checkov failure will prevent automatic image publication without adding another image-workflow condition.

### 6. Retain evidence without requiring GitHub Code Scanning

Always retain JSON and SARIF as ordinary GitHub Actions artifacts. This works without `security-events: write` and does not depend on GitHub Advanced Security availability.

After the artifact path is proven, separately determine whether the CBIIT repository permits SARIF upload to GitHub Code Scanning. If permitted, add that presentation layer without making it the only evidence location.

Each result set should identify:

- source commit SHA;
- Checkov version;
- configuration hash or version;
- scanned root;
- passed, failed, and skipped counts;
- active suppressions; and
- workflow run URL or ID.

### 7. Govern suppressions as reviewed exceptions

Prefer remediation. When a Checkov policy is not applicable or conflicts with an approved architecture decision, place the suppression on the narrowest affected Terraform resource.

Every suppression must include:

- the Checkov policy ID;
- a concrete technical reason;
- an issue, ADR, risk, or decision reference;
- an accountable owner; and
- a review or expiration date.

The implementation should add a small validation step that rejects malformed or undocumented `checkov:skip` annotations. Generic explanations such as `not applicable`, `false positive`, or `accepted risk` are insufficient without supporting detail.

Do not use a repository-wide baseline as the permanent solution to initial findings. A temporary report from the implementation branch may be used to classify findings, but the merged gate must be blocking.

### 8. Reuse the same scanner before privileged planning

The first pull request should establish the CI gate. After it is stable, reuse the same locked wrapper in:

- `.github/workflows/bootstrap-cloud-one.yml`, before creation of the exact initialization plan; and
- `.github/workflows/deploy.yml`, before creation of the exact runtime plan.

This closes the gap where a privileged manual workflow might run from a main commit whose CI is still running or has failed. The workflows must call the wrapper rather than duplicate Checkov flags. Their uploaded plan artifacts should include the matching Checkov summary or evidence manifest.

If those repeated workflow steps become noisy, extract only the setup and wrapper invocation into a small local composite action. Do not begin with a new abstraction unless the three workflows demonstrate meaningful duplication.

## Failure policy

### Initial policy

The first integration runs Checkov locally without a Prisma Cloud API key. In this mode, platform severity filtering is not available. The honest initial policy is therefore:

- every non-suppressed failed policy blocks the job;
- a scanner crash, missing root, missing report, or installation failure blocks the job;
- an approved resource-level suppression is reported as skipped and does not block; and
- no finding is silently downgraded based on a severity label the local scanner cannot authoritatively provide.

If NCI later provides Prisma Cloud access and approved enforcement rules, severity-based hard and soft failures can be evaluated as a separate change. That change must not be assumed in this implementation.

### Scanner availability

Pull requests and main CI should fail closed when the locked scanner cannot run. A security gate that silently passes during an installation or execution failure is not a gate.

The manual bootstrap and deployment workflows should also fail closed once Checkov is added to them. Emergency bypass, if one is ever required, must be a reviewed repository change or an explicitly governed break-glass procedure, not a workflow input that any operator can toggle.

## Initial finding workflow

1. Build the locked tool environment and wrapper on the implementation branch.
2. Run all four roots and save the first complete report.
3. Classify every finding as:
   - remediate in Terraform;
   - justified resource-level suppression;
   - Checkov configuration defect; or
   - upstream scanner defect requiring a narrow temporary exception.
4. Fix the infrastructure configuration where the change is safe and within scope.
5. Add documented suppressions only after confirming the architecture and compensating control.
6. Re-run until the intended hard-fail policy passes.
7. Add the blocking CI job before the pull request merges.

If the first scan reveals too many unrelated remediations for one reviewable pull request, keep the work on an implementation branch and split remediation commits or pull requests by finding family. Do not merge a permanently non-blocking Checkov job merely to reduce the immediate workload.

## Test plan

### Wrapper tests

- Verify the wrapper scans exactly the four declared roots.
- Add a temporary failing fixture and prove the wrapper exits nonzero.
- Add a documented suppression fixture and prove it appears as skipped.
- Prove the wrapper continues scanning later roots after an earlier failure.
- Prove missing JSON or SARIF output causes failure.
- Prove a newly introduced root causes the root-coverage check to fail.

### CI tests

- Run on an internal pull request with no AWS or Prisma credentials.
- Run on a fork pull request and confirm no private GitHub dependency credentials are requested.
- Confirm artifacts upload on both success and failure.
- Confirm the `Required CI gate` fails when `iac-security` fails.
- Confirm a successful main run can still publish the reviewed image.
- Confirm a failed Checkov main run cannot reach image publication.

### Infrastructure regression tests

- Run the existing OpenTofu format, validate, test, deployment-flow, and shell-syntax checks after every remediation.
- Review every Terraform change for resource replacement, deletion, permissions expansion, availability impact, or cost impact.
- Generate and review the normal OpenTofu plan before applying a remediation that changes AWS resources.

## Implementation sequence

### Phase 1 Tooling and local execution

- [x] Add `tools/checkov/pyproject.toml` with the exact approved Checkov version.
- [x] Generate and commit `tools/checkov/uv.lock`.
- [x] Add `.checkov.yml`.
- [x] Add the explicit root manifest.
- [x] Add `scripts/check-iac-security.sh`.
- [x] Add `just checkov`.
- [x] Document the local command and output locations.

### Phase 2 Finding triage and remediation

- [x] Run the first complete four-root scan.
- [x] Save and review the initial result set.
- [x] Classify every finding.
- [x] Remediate valid findings.
- [x] Add only approved, documented resource-level suppressions.
- [x] Re-run all OpenTofu tests and review infrastructure changes.

### Phase 3 Required CI gate

- [x] Add the `iac-security` job to `.github/workflows/ci.yml`.
- [x] Upload JSON and SARIF artifacts with `if: always()`.
- [x] Add the job result to the existing required gate.
- [ ] Verify internal and fork pull-request behavior.
- [ ] Verify Checkov failure blocks main image publication.

### Phase 4 Privileged workflow defense in depth

- [x] Reuse the same wrapper before bootstrap plan creation.
- [x] Reuse the same wrapper before runtime plan creation.
- [x] Bind the Checkov evidence to the reviewed source and plan artifacts.
- [x] Confirm scanner failure blocks privileged planning and apply.

### Phase 5 Review and closeout

- [x] Run the complete local test plan.
- [ ] Verify the pull-request CI test plan.
- [ ] Request adversarial review of the implementation pull request.
- [ ] Resolve every review finding.
- [ ] Merge only after the required gate passes.
- [ ] Update the Cloud One migration tracker with the pull request, Checkov version, scan roots, active suppressions, evidence location, and completed checkboxes.

## Acceptance criteria

- [x] Checkov lives in `CBIIT/data_chord` as a separately locked tool project, not in the application dependency environment.
- [x] One documented local command and CI use the same version, configuration, root manifest, and wrapper.
- [x] All four OpenTofu roots are scanned independently.
- [x] The scan works without AWS credentials, Prisma credentials, GitHub App credentials, or private dependency access.
- [x] Any non-suppressed failure or scanner error fails the required CI gate.
- [x] JSON and SARIF reports are retained on successful and failed runs.
- [x] Suppressions are narrow, justified, owned, dated, and visible in the result set.
- [x] A new committed OpenTofu root cannot silently escape scanning.
- [x] A failed Checkov run prevents main image publication.
- [x] Bootstrap and runtime planning reuse the same scanner before privileged AWS work.
- [x] Existing OpenTofu tests remain green after finding remediation.
- [ ] The overall migration tracker is updated only after the implementation and evidence are verified.

## Open decisions that do not block the first implementation

- Whether CBIIT permits SARIF upload to GitHub Code Scanning in addition to artifact retention.
- Whether evidence retention should remain 14 days or use a longer Fast ATO retention period.
- Whether NCI will later supply Prisma Cloud platform credentials and enforcement rules.
- Whether GitHub Actions, Dockerfile, secrets, or additional IaC formats should receive separate Checkov coverage.
- Whether repeated setup in three workflows eventually justifies a local composite action.

## Official references

- [Checkov CLI command reference](https://www.checkov.io/2.Basics/CLI%20Command%20Reference.html)
- [Checkov installation guidance](https://www.checkov.io/2.Basics/Installing%20Checkov.html)
- [Checkov suppression and skip guidance](https://www.checkov.io/2.Basics/Suppressing%20and%20Skipping%20Policies.html)
- [Checkov GitHub Actions integration](https://www.checkov.io/4.Integrations/GitHub%20Actions.html)
- [Checkov SARIF output](https://www.checkov.io/8.Outputs/SARIF.html)
- [Checkov package and supported Python versions](https://pypi.org/project/checkov/)
