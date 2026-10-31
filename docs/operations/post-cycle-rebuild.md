# Retained-state rebuild prerequisites after 29 October

This is a source handoff, not authority to restart RDS, recreate runtime, publish static assets or mutate state. The dated cost-down receipt last verified RDS stopped and protected at **29 October 2026, 20:14:57 Costa Rica**, with automatic restart expected **5 November at 20:14:57 Costa Rica**. No new AWS status is claimed here. Data, three retained snapshots, parameter/subnet groups, database SG and required VPC were preserved.

## Restore database network access explicitly

`infra/live/dev/rds/terragrunt.hcl` now keeps `allowed_security_group_ids = []` and has no EKS/management dependencies. This matches the retained stopped state and prevents a routine RDS plan from silently recreating stale ingress. The recorded native cost-down plan deleted exactly two PostgreSQL ingress rules; no DB instance, DB SG, parameter, subnet-group, backup or data change was included. Source does not stop a running database or prevent its scheduled automatic restart.

Before a future separately authorized reconstruction:

1. Verify the retained DB's current generation, status, protection and remote state, then rebuild the independently authorized EKS/management prerequisites.
2. Restore the two Terragrunt dependency blocks pointing to `../eks` and `../management`. Set `allowed_security_group_ids` to their newly verified `cluster_security_group` and `security_group_id` outputs. Use real outputs, no historical IDs or mocks as deployment evidence.
3. Save/review a native RDS plan. Permit only the required TCP/5432 ingress rules from those current owned SGs. Require no instance/SG replacement, parameter, backup, master-secret, deletion-protection or data change. Stop for any other operation. Apply only under a fresh authorization covering that exact plan.
4. Prove private PostgreSQL TLS before phase 2. Empty ingress intentionally blocks database bootstrap and application connectivity; do not start bootstrap first or relax public/CIDR access to bypass it.

## Platform-owned ALB readiness

Phase 2 labels both new and existing `apps` namespaces before addon installation. It does not restart existing pods, alter Deployment rollout policy, change RBAC or install an executor. LBC injection requires matching Services and existing IP TargetGroupBindings; labeling alone does not make the first installation ALB-aware. Verify server-side admission with the real selectors and watch new pod IPs, gate conditions and actual ALB health during a later authorized rollout. The strict HTTP 400/ProblemDetails/request-ID smoke remains unchanged.

## NAT generation and retained identities

The cycle-specific local activation commit is preserved separately, not promoted as a reusable default. Its old predecessor ENIs must not be copied into a new generation blindly. The recorded final CONTROL was disabled and journals READY; preserve generation history, ownership, guards, protected DynamoDB and the failure queue. Review fresh native plans before any reactivation. The known output issue for a missing SSM profile and broad destroy dependency on retained CONTROL are separate unresolved source concerns; do not bypass them using state removal or protection changes.

## Independent hosting and diagnostic patch

The CloudFront source removes only the empty legacy `s3_origin_config.origin_access_identity`; the existing `origin_access_control_id` remains authoritative for private S3. The earlier provider/state normalization is not an origin migration. A later plan must preserve the distribution, bucket, OAC, API-disabled DEMO selection and all retained versions. No Terraform/state operation is performed by this PR.

The local HTTP 504 diagnostic patch and its tests remain outside this PR. It preserves unexpected HTTP status without reading bodies, but changing the installed executor requires a separately reviewed bundle/hash/version and environment-contract plan. Do not update installed hashes or reuse old installation evidence automatically.

See [private delivery readiness](private-cd.md#alb-pod-readiness-gates), [manual cleanup](lab-cleanup.md), [NAT recovery guards](nat-recovery.md) and [independent hosting ownership](../../infra/portfolio/frontend-static/README.md). Historical absence statements in those documents are not a new inventory. Existing AWS delivery workflows must remain disabled until separately authorized.
