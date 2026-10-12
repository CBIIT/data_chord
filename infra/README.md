# Data Chord AWS infrastructure

This directory owns three application infrastructure roots. The separate
[`datachord-infrastructure`](https://github.com/CBIIT/datachord-infrastructure)
repository owns the AWS account foundation.

See [../DEPLOYMENT.md](../DEPLOYMENT.md) for the operator procedure.

## Ownership

The account foundation provides:

- the versioned OpenTofu state bucket;
- one `/foundation/<name>-deployer` role;
- the deployer permission boundary;
- the application-role permission boundary; and
- the `/application/` IAM path.

The full root in `infra/` provides:

- the application VPC, load balancer, DNS record, certificate, and Cognito;
- ECS, ECR, CodeBuild, CloudWatch logs, and their IAM roles;
- the application workflow S3 bucket; and
- three DynamoDB tables for reference data, harmonization results, and CDE
  recommendations.

The foundation does not deploy application resources. The application
deployment does not create or change the foundation.

The `infra/cloud-one/` root is the initial CBIIT non-production deployment. It
creates the selected middle tier plus its private runtime:

- an immutable, scan-on-push ECR repository;
- one workflow S3 bucket and three DynamoDB tables;
- an ECS cluster, CloudWatch log group, bounded task roles, and (after network
  completion) one private Fargate service; and
- no VPC, public IP, load balancer, DNS, certificate, Cognito user pool, or
  public endpoint.

Bootstrap and runtime share
`datachord/<target>/<stage>/cloud-one/tofu.tfstate`. Bootstrap deliberately
leaves the ECS service disabled so ECR and the data plane can be created before
the first image exists and before the VPC ticket completes. Runtime enablement
requires an immutable image digest, a VPC id, and at least two private subnets.

The separate `infra/customer-platform/` root remains available for providers
that own their runtime. It creates only the shared data-plane module:

- one workflow S3 bucket;
- one S3 public-access block; and
- three DynamoDB tables.

It creates no IAM role, network, compute, registry, TLS, authentication, or
logging resource. It accepts either the foundation schema-v2 handoff or the
checked-in environment contract and uses
`datachord/<target>/<stage>/customer-platform/tofu.tfstate`. Its outputs give
the customer the runtime environment and policies for customer-owned roles.

## Environment contract

Each deployment reads one strict file:

```text
environments/<target>/<stage>.json
```

The target and stage come from the path. The stage must be `dev`, `qa`,
`staging`, or `prod`. The state key is always:

```text
datachord/<target>/<stage>/tofu.tfstate
```

The environment file contains application inputs, secret names, and selected
foundation outputs. It does not contain secret values, reference data, a state
key, or a CodeConnections ARN. `infra/scripts/environment.py` rejects missing
and extra fields.

The deployer role and application boundary must use the same foundation name
prefix. The deployment derives the deployer boundary from that prefix and
checks the live foundation before it plans.

The Cloud One root uses the narrower
`infra/scripts/cloud_one_environment.py` contract. Its checked-in file carries
only non-secret account, state, permissions-boundary, and network identifiers.
`vpc_id: null` and an empty `private_subnet_ids` list are valid only for
bootstrap; the runtime command fails closed until they are replaced with the
approved VPC ticket values.

## Mutation safety

The `plan` command validates the source commit, environment, AWS identity,
foundation, and state. It displays a read-only resource forecast and saves
`.plans/<target>-<stage>.json`. It does not apply resources or build an image.

The receipt binds the forecast to the environment file, Git commit, AWS
account, Region, state location, and state lineage and serial.

The `deploy` command has no confirmation prompt. It rejects a changed receipt
or state, then:

- marks the receipt in progress before the first AWS change;
- creates and checks a saved prerequisite plan;
- builds or reuses an image tagged with the full Git commit;
- creates and checks a saved application plan; and
- waits for a stable ECS service and healthy load-balancer targets.

Each internal plan must stay inside the reviewed forecast. An unexpected
resource, deletion, or replacement stops the deployment before apply. The only
allowed replacement is the normal ECS task-definition revision for a new
image.

If a deployment stops after its first AWS change, the receipt remains in
progress. Inspect the failure and run `plan` again before a retry.

## Data and users

Deployment creates an empty reference-data table. Loading reference data is a
separate controlled operation. It is not an OpenTofu input.

The deployment also creates the Cognito user pool. User invitations are a
separate operation.

See [../DEPLOYMENT.md](../DEPLOYMENT.md) for the supported reference-data and
user-invitation commands.

## Current limits

- The application deployment rejects AWS GovCloud because ALB Cognito
  authentication is unavailable there. The account foundation can still be
  created in GovCloud.
- A deployment requests a four-hour deployer-role session. Before apply, it
  checks that at least three hours remain.
- A CI job that starts with the deployer role must set
  `AWS_CREDENTIAL_EXPIRATION` to the ISO 8601 STS expiration time.
- The environment owner controls the AWS profile, DNS delegation, GitHub App,
  programmatic API key, CodeConnections source credential, Bedrock access, and
  any controlled CI runner.
