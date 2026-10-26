# DataChord dev deployment status

This is the working record for the first `cbiit/dev` deployment. Update it as
the release advances or a new issue is found.

## Target

- Date started: 2026-10-26
- AWS account: `211125567571` (`NIH.NCI.CBIIT.CRDC-DATA-MGMT.NONPROD`)
- Region: `us-east-1`
- VPC: `vpc-29a12251` (`vpc-dev-us-east-1`)
- Private ECS subnets: `subnet-4f35f112` and `subnet-409a0424`
- Deployment profile: private dev, one Fargate task, no load balancer or public ingress

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
- Raise the audited Python dependency floors for `certifi`, `filelock`, and
  `virtualenv`; explicitly record the temporary non-runtime `setuptools`
  exception described below.

## Open issues and follow-up

1. **The current reference data is synthetic.** It is sufficient for this
   no-user dev proof and the deployment smoke test, but must be replaced or
   superseded by an approved canonical catalog before real users or data are
   introduced.
2. **Private egress is not yet proven from Fargate.** The route-table inspection
   is encouraging, but the deployment smoke task is the authoritative check for
   ECR, S3, DynamoDB, CloudWatch Logs, STS, and Bedrock reachability.
3. **Bedrock model access is unverified.** The smoke task must confirm access to
   GPT-5.6 Luna and GPT-5.6 Sol in `us-east-1`.
4. **The requested DataChord-specific AWS accounts are not visible in the AWS
   access portal.** This first deployment therefore uses the existing CRDC Data
   Management non-production account listed above. Migration to account
   `701016785834` requires access and a separately bootstrapped environment.
5. **The VPC is shared.** Its owner is AWS account `019211168375`; DataChord can
   deploy workloads into the shared subnets but does not manage the underlying
   network.
6. **There is no user login endpoint yet.** The initial service has no load
   balancer, public ingress, Cognito, DNS, or TLS endpoint. Successful deployment
   proves the private runtime and its dependencies, not end-user access.
7. **One audit exception is time-limited.** `setuptools` is present only through
   the optional local-inference test extra and is not installed in the deployed
   Bedrock image. Its fix for `GHSA-xmj3-9gf7-h52w` is still inside the enforced
   seven-day package quarantine. CI records an explicit exception through
   2026-10-27; update the lock and remove it once the fixed release is eligible.

## Release checkpoints

- [ ] Configuration and vulnerability-remediation changes merged to `main`
- [ ] Immutable application image published and ECR scan gate passed
- [ ] Exact OpenTofu runtime plan created and reviewed
- [x] Dev reference catalog populated with the synthetic demo standard
- [ ] Runtime plan applied through the protected `dev` GitHub environment
- [ ] ECS service stable at one desired task
- [ ] S3, DynamoDB, reference catalog, and Bedrock smoke checks passed
