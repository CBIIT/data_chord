# DataChord dev deployment status

This is the working record for the first `cbiit/dev` deployment. Update it as
the release advances or a new issue is found.

## Target

- Date started: 2026-10-26
- AWS account: `211125567571` (`NIH.NCI.CBIIT.CRDC-DATA-MGMT.NONPROD`)
- Region: `us-east-1`
- VPC: `vpc-29a12251` (`vpc-dev-us-east-1`)
- Private ECS subnets: `subnet-4f35f112` and `subnet-409a0424`
- Deployment profile: private dev, one Fargate task, internal HTTP ALB, no
  public ingress or production authentication

## Verified before runtime deployment

- The foundation state bucket and Cloud One bootstrap have already been deployed.
- ECR, the ECS cluster, CloudWatch log group, S3 workflow bucket, application
  IAM roles, and three DynamoDB tables have been created.
- The two selected private web-application subnets are available, belong to the
  dev VPC, span two Availability Zones, and do not assign public IP addresses.
- The shared route table sends `0.0.0.0/0` through the Cloud One transit gateway
  and includes an S3 VPC endpoint.
- The Bedrock catalog contains GPT-5.6 Luna and GPT-5.6 Sol, and both corresponding
  US inference profiles report `ACTIVE`. Runtime invocation by the ECS task role
  remains part of the deployment smoke test.
- `data-chord-dev-reference-data` is active with deletion protection and PITR.
  It initially contained zero items. The committed synthetic demo catalog was
  loaded as one atomic, conditional transaction and then verified with three
  catalog rows and 13 total rows. Its source SHA-256 is
  `13c6e8da5368f8cf0257386b805b2832f7c2ec6d5feb217216f31cf0c38609fa`.

## Changes prepared for this deployment

- Record the confirmed VPC and private subnet IDs in
  `environments/cbiit/dev.json`.
- Move the runtime image to a pinned Amazon Linux 2023 base and update affected
  JavaScript dependencies so the ECR critical/high vulnerability gate can pass.
- Add a container build and smoke check to CI.
- Pin the Playwright E2E job to Ubuntu 24.04 after GitHub's `ubuntu-latest`
  image advanced to unsupported Ubuntu 26.04.
- Raise the audited Python dependency floors for `certifi`, `filelock`,
  `setuptools`, and `virtualenv`, and update all build paths to the uv release
  that removes the compromised emSign trust root.
- Apply the approved, exact-artifact package-age exceptions for certifi
  `2026.10.19` and setuptools `84.2.1`. The fixed cutoffs do not admit later
  releases and are scheduled for removal after 2026-10-27T19:02:00Z.

## Deployment attempts

- GitHub Actions run `40387666095` passed preflight and built the production
  image from merged commit `5dbcbd8`. It uploaded every image layer, then ECR
  rejected Docker's final referenced-manifest lookup with `403 Forbidden`.
  Plan and apply were skipped, so no runtime resources changed. The scoped
  build session was missing `ecr:BatchGetImage`; the follow-up adds only that
  repository-level read action.
- GitHub Actions run `40389486957` passed preflight, built the production image
  from merged commit `81a7c00`, and published OCI index digest
  `sha256:4600955d6b7e2ff1d6b8507bba5fafb3a8dd2fb257e50d0acaf2e6046e02f7cc`.
  ECR did not expose basic scan findings for that OCI index within the guarded
  60-second window, so plan and apply were again skipped. The follow-up disables
  BuildKit provenance for the deployable image so ECR receives a directly
  scannable single-platform image manifest; the ECR vulnerability gate remains
  mandatory.
- GitHub Actions run `40390606889` passed preflight, published directly
  scannable image digest
  `sha256:c60620690d2ce462aa04ad75aa67826ca883f3b75ffa2c4b20896c183115c7fc`,
  and completed the ECR scan. The scan correctly blocked plan and apply after
  reporting zero critical and 33 high findings, all in Amazon Linux RPMs. A
  live repository check showed newer builds for every affected package, so the
  follow-up advances both pinned image stages from AL2023 `2023.12.20260831` to
  the immutable `2023.12.20261016` release and pins the patched RPM builds from
  the live AL2023 repository instead of weakening the scan gate.
- GitHub Actions run `40393405239` published image digest
  `sha256:7452b0358fb5bab1a672a2ec9f2aba667a5aece2eaa62f07de709f1ccdbed31d`,
  passed the ECR vulnerability gate with no critical or high findings, and
  applied the first runtime plan. OpenTofu added the service security group,
  task definition `data-chord-dev:1`, and ECS service. The service stabilized
  at one task, but the final smoke task stopped at its first Bedrock invocation:
  the account had not yet accepted the AWS Marketplace subscription used by
  the selected OpenAI models. The ECS task role was deliberately not granted
  Marketplace subscription permissions. An administrator instead established
  account-level access by successfully invoking both selected US inference
  profiles. A failed-job rerun correctly refused to reuse the now-stale saved
  plan after the successful state change.
- GitHub Actions run [`40395043600`](https://github.com/CBIIT/data_chord/actions/runs/40395043600)
  completed the release end to end from merged commit `d9ee33a`. It reused the
  exact immutable image above, passed the ECR scan, created fresh reviewed plan
  SHA-256 `cf8ff6504816766a3c340d71da83c77af9d07fe8eff37191a7391867782ee5e1`,
  and applied it with zero infrastructure changes. The ECS service remained
  stable at one running task. The live Fargate smoke task exited successfully,
  proving the application task role, private-network egress, S3, DynamoDB,
  reference catalog, and both GPT-5.6 inference profiles.
- GitHub Actions run [`40522279182`](https://github.com/CBIIT/data_chord/actions/runs/40522279182)
  created the internal ALB, listener, target group, and security-group path, but
  the new ECS task repeatedly exited before it could become healthy. Live ECS
  logs identified a configuration-name mismatch: the task definition supplied
  `DATA_CHORD_DEV_MODE=true`, while application startup deliberately requires
  `DEV_MODE=true` before it permits shared identity in a hosted profile. PR
  [#11](https://github.com/CBIIT/data_chord/pull/11) corrected the task
  definition and its OpenTofu contract test.
- GitHub Actions run [`40527532600`](https://github.com/CBIIT/data_chord/actions/runs/40527532600)
  completed the corrected internal-preview release from merged commit
  `8a63ed0`. It published ECR image
  `sha256:d98c068aeeef0e501cc6fe47f9660f19e901f68ee211b63d905a264d05643f4c`,
  applied the exact reviewed plan, stabilized ECS task definition revision 3,
  and verified one healthy ALB target. The live Fargate smoke task again proved
  S3, DynamoDB, the reference catalog, and both selected model profiles. The
  resulting private preview URL is
  `http://internal-data-chord-dev-internal-196848599.us-east-1.elb.amazonaws.com`.

## Open issues and follow-up

1. **The current reference data is synthetic.** It is sufficient for this
   no-user dev proof and the deployment smoke test, but must be replaced or
   superseded by an approved canonical catalog before real users or data are
   introduced.
2. **The requested DataChord-specific AWS accounts are not visible in the AWS
   access portal.** This first deployment therefore uses the existing CRDC Data
   Management non-production account listed above. Migration to account
   `701016785834` requires access and a separately bootstrapped environment.
3. **The VPC is shared.** Its owner is AWS account `019211168375`; DataChord can
   deploy workloads into the shared subnets but does not manage the underlying
   network.
4. **The internal preview is intentionally not a production user endpoint.** It
   uses HTTP and a fixed shared dev identity, has no Cognito, TLS certificate, or
   friendly DNS name, and accepts ALB ingress only from the dev VPC CIDR
   `10.208.0.0/21`. The ALB target is healthy, but a browser test from the current
   workstation returned `ERR_ADDRESS_UNREACHABLE`. If workstation access is
   required, the network team must confirm a routed NCI/VPN path to the private
   ALB subnets and the approved VPN/client source CIDR; that CIDR can then replace
   or augment the VPC-only allowlist. No public or external-internet endpoint is
   requested for dev.
5. **Two third-party Actions still target deprecated Node.js 20.** GitHub forced
   `actions/create-github-app-token` and the artifact upload/download actions to
   Node.js 24 during this release. The run passed, but their pinned versions
   should be advanced when compatible releases are available.

## Release checkpoints

- [x] Configuration and vulnerability-remediation changes merged to `main`
- [x] Immutable application image published and ECR scan gate passed
- [x] Exact OpenTofu runtime plan created and reviewed
- [x] Dev reference catalog populated with the synthetic demo standard
- [x] Runtime plan applied through the protected `dev` GitHub environment
- [x] ECS service stable at one desired task
- [x] S3, DynamoDB, reference catalog, and Bedrock smoke checks passed
- [x] Internal ALB, listener, target group, and least-privilege security-group
      path deployed across the two approved private subnets
- [x] ECS registered exactly one healthy target and exposed the internal dev URL
