# Infrastructure as code

[Architecture](current-platform.md) · [Deployment](../operations/deployment.md) · [Lab cleanup](../operations/lab-cleanup.md)

`infra/modules/` contains reusable AWS modules; `infra/live/dev/` contains 18 Terragrunt stacks. `root.hcl` generates the AWS provider and an S3 backend key per stack (`<environment>/<stack>/terraform.tfstate`). State is encrypted and versioned in S3; DynamoDB supplies locking/checksums. State and backend creation are distinct from runtime infrastructure.

## Stack dependency reference

The table includes output dependencies and ordering-only `dependencies` blocks. It is an apply DAG, not a list of simultaneously deployable units.

| Stack | Module | Prerequisite stacks |
| --- | --- | --- |
| `vpc` | `vpc` | — |
| `nat` | `nat-egress` → `nat` | vpc |
| `s3` | `s3` | — |
| `ecr` | `ecr` | — |
| `event-encryption` | `event-encryption` | — |
| `sqs` | `sqs` | event-encryption |
| `eventbridge` | `eventbridge` | sqs |
| `eks` | `eks` | vpc, nat |
| `api-gateway-authorizer-secrets` | `authorizer-secrets` | — |
| `runtime-secrets` | `runtime-secrets` | eks, api-gateway-authorizer-secrets |
| `api-gateway-authorizer` | `lambda` | api-gateway-authorizer-secrets |
| `iam` | `iam` | eks, sqs, eventbridge, event-encryption |
| `apigateway-core` | `apigateway-core` | vpc, api-gateway-authorizer |
| `management` | `management-host` | vpc, eks, s3, apigateway-core |
| `rds` | `rds` | vpc, eks, management |
| `private-cd` | `private-cd` | management, s3, ecr |
| `observability` | `observability` | eks, apigateway-core, rds |
| `apigateway-integration` | `apigateway-integration` | apigateway-core, vpc; healthy LBC ALB outside Terraform |

The 19 module directories include the nested `nat` implementation; there are 18 live stacks. Module/provider locks are committed for Linux and Windows amd64. Mock dependency outputs support selected static commands; `output` is excluded so generated inventory cannot adopt fixtures as real resources.

## Configuration and account prerequisites

[env.hcl](../../infra/live/dev/env.hcl) sets region/project/environment, cluster name, NAT mode, JWT issuer/audience and database name. Network CIDRs, EKS/addon pins and RDS sizing are in the corresponding live stacks. Helm defaults and the dev overlay supply application settings; generated output overlays supply environment-specific IDs. The prod Helm overlay is a validation template, not a provisioned environment.

Some account dependencies are external: temporary operator roles, permissions-boundary policies and effective bootstrap/EKS access. Live EKS, management and private-CD inputs reference named `cnp-cert-*` boundary policies. [Operator policy documents](../../infra/operator-policies) are reference inputs, not automatic account bootstrap. Several bind specific retired resource IDs. Recreate authorized roles/boundaries and rebind exact new resources; copying those documents verbatim is not a portable installation procedure. The teardown guard pins reviewed construction changes, so functional reconfiguration also requires deliberate guard review.

The backend naming convention includes the effective account ID. `scripts/bootstrap-terraform-backend.sh` creates/configures the backend and mutates AWS; it is not a validation script. Phase 0 only verifies it. Keep credentials, generated values, binary plans and state out of Git.

Instance-mode NAT now exposes ASG slot names rather than static member IDs. The launch recovery controller owns EIP associations/private default targets; Terraform retains allocations, launch templates and ASGs. Admission defaults off, and the partially retired state requires a separately reviewed [migration](../operations/nat-recovery.md). No state reconciliation or live recovery occurred with this source change.

## Reproducibility contract

Bootstrap applies 15 core stacks interactively, installs platform resources, deploys digest-selected applications, discovers the ALB, then applies API integration. Phase 2 applies `observability` when the CloudWatch addon is absent; `private-cd` is a separate operator apply. There is no unattended account-to-application installer.

Generated `.generated/dev/environment.json` is a closed, non-secret contract derived from real Terraform outputs and account identity. Its schema checks region/account/ARN consistency; generated Helm overlays are disposable. IDs must be regenerated after replacement. Secret values remain in Secrets Manager and application releases use immutable ECR digests/S3 VersionIds.

Pinned versions include Terraform 1.13.4, Terragrunt 0.93.3, .NET SDK 10.0.402, EKS 1.35, RDS PostgreSQL 15.18, Helm 4.2.2 and kubectl 1.35.0. The EKS AMI/addon versions are explicit in the live EKS stack. Chart dependencies are pinned in Chart.yaml/Chart.lock. GitHub Actions use commit SHAs. CI uses PostgreSQL 15.18; the earlier resilience/concurrency report separately records disposable local PostgreSQL 17.

SDK/runtime images are digest-pinned. Some inputs remain dynamic: hosted runner/tool patch versions, Lambda's runtime-provided AWS SDK and AWS-controlled platform patches. The NAT AMI is region-specific. Check pin availability before a future deployment. Identical source does not promise byte-identical rebuilt container layers or identical AWS-generated IDs.

## Destruction is an operational DAG

Reversing Terragrunt alone cannot remove controllers' resources safely. Freeze delivery and writers, export evidence/data, remove gateway integration, converge Ingress/ALB cleanup while LBC exists, remove application/platform consumers, prepare protected RDS only if it is selected for deletion, close private Kubernetes observation, then retire management/EKS/network and residual storage. Keep the backend until independent verification is possible. [Lab cleanup](../operations/lab-cleanup.md) documents the manual owner order and retention boundaries.
