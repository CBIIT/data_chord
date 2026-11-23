# Checkov Exception Register

This register explains every policy exception accepted by the DataChord
infrastructure scan. The inline `checkov:skip` annotation remains the enforcing
control and contains the accountable owner and review date. Exceptions must be
removed when the control is implemented or renewed through pull-request review
before the listed date.

**Owner:** DataChord Engineering

**Next review:** 2027-02-28

## Cloud One decisions still required

| Policy | Affected resources | Why the exception exists | Resolution condition |
| --- | --- | --- | --- |
| `CKV_AWS_158` | Application and CodeBuild CloudWatch log groups | Cloud One has not supplied an approved customer-managed logging key or key-administration model. AWS-managed encryption remains active. | Configure the approved KMS key and remove the exceptions. |
| `CKV_AWS_338` | Application and CodeBuild CloudWatch log groups | The authoritative retention duration remains an NCI security and records-management decision. The current development default is 14 days. | Apply the approved environment retention periods. |
| `CKV2_AWS_11` | Legacy full-application VPC | The destination, retention, and operating owner for VPC flow logs are not yet defined. | Configure the approved flow-log destination and retention. |
| `CKV_AWS_136` | ECR repositories | Cloud One has not supplied the approved customer-managed ECR key or cross-account key policy. ECR encryption remains enabled with the AWS-managed key. | Configure the approved KMS key and remove the exceptions. |
| `CKV_AWS_91` | Application load balancers | The centralized access-log bucket, retention period, and log owner are not yet available. | Configure access logging to the approved destination. |
| `CKV2_AWS_28` | Legacy public application load balancer | The WAF policy and service ownership model remain an external security decision. | Associate the approved WAF web ACL. |
| `CKV_AWS_119` | DynamoDB data-plane tables | Cloud One has not supplied an approved customer-managed DynamoDB key or key-administration model. DynamoDB encryption remains enabled with the AWS-owned key. | Configure the approved KMS key and remove the exceptions. |
| `CKV_AWS_18` | Workflow S3 bucket | The centralized S3 access-log destination and retention policy remain undefined. | Configure bucket access logging to the approved destination. |
| `CKV2_AWS_61`, `CKV_AWS_21` | Workflow S3 bucket | Workflow retention, recovery, and deletion periods remain governance decisions. Enabling lifecycle rules or versioning without those periods would encode an unsupported policy. | Implement the approved lifecycle and recovery policy. |
| `CKV_AWS_144` | Workflow S3 bucket | Cross-region replication and disaster-recovery requirements remain undefined. | Implement the approved replication and recovery design, or record a renewed no-replication decision. |
| `CKV_AWS_145` | Workflow S3 bucket | Cloud One has not supplied an approved customer-managed S3 key or key-administration model. S3 encryption remains enabled by AWS. | Configure the approved KMS key and remove the exception. |

## Time-bounded development architecture

| Policy | Affected resources | Why the exception exists | Resolution condition |
| --- | --- | --- | --- |
| `CKV_AWS_150` | Legacy and Cloud One development ALBs | Development load balancers are intentionally replaceable while the managed endpoint is being established. | Enable deletion protection before promotion beyond development. |
| `CKV2_AWS_20`, `CKV_AWS_2`, `CKV_AWS_103` | Cloud One internal development listener | The internal, no-user preview remains HTTP-only until Cloud One certificate and DNS requests complete. Access is constrained by the internal ALB and network path. | Install the managed certificate, use HTTPS, and remove all three exceptions. |
| `CKV_AWS_333` | Legacy full-application ECS service | This non-Cloud-One root still runs Fargate tasks in routed subnets and needs public task addresses for outbound access. The Cloud One runtime uses private subnets. | Move the legacy service to private subnets with approved egress, or retire the root. |

## Intentional design exceptions

| Policy | Affected resources | Why the exception exists | Resolution condition |
| --- | --- | --- | --- |
| `CKV2_AWS_62` | Workflow S3 bucket | DataChord does not use object-event processing; application requests explicitly control workflow operations. | Reassess if an event-driven workflow is introduced. |

Exceptions for stable implementation choices—such as Docker-in-Docker in the
dedicated CodeBuild image project and TLS termination at the ALB—are documented
next to their design in `CHECKOV_IMPLEMENTATION_PLAN.md`.
