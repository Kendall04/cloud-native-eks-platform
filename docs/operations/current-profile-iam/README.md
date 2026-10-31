# IAM prerequisites for the bounded current-profile AWS session

Review-only proposal, 16 October 2026. These JSON files have **not** been applied. Use only profile `cnp-cert-dev`, expected account `341936017254`, region `us-east-1`. The [session plan](../current-profile-aws-validation.md) defines the 17-stack runtime, acceptance, USD 8/six-hour envelope and retirement. Nothing here authorizes a deployment or GitHub publication.

## Recovery and exact differences

Git history across all local refs contains management/private-CD boundary files, but no EKS/app boundary definitions. Bounded filename searches of the checkout's ignored validation evidence on Windows and Linux also found no EKS/app boundary files. A subsequent read-only CloudTrail lookup recovered the documents, avoiding invented replacement permissions:

| Proposal | Recovered source | Difference from recovered/current definition |
| --- | --- | --- |
| `cnp-cert-eks-workload-boundary.json` | CreatePolicy event `4fbb3be8-909f-41f9-832c-fecca2dd5729`, 13 October 2026 01:58:54 UTC | None; 138 explicit actions, same resources and conditions |
| `cnp-cert-app-workload-boundary.json` | CreatePolicyVersion event `bb3ef0ff-4348-4721-9e52-16d6adfb6f14`, 13 October 2026 15:54:39 UTC, `setAsDefault=true` | None; the later historical default already corrected both authorizer secret paths |
| `cnp-cert-management-workload-boundary.json` | [Versioned management boundary](../../../infra/operator-policies/cnp-cert-management-workload-boundary.json) | None; canonical JSON comparison is enforced |

The app's earlier creation event used obsolete hyphenated secret names. Looking up its **ARN**, rather than only its name, revealed the later version. The proposal restores that later document; it does not union the legacy and current secret paths. No new IAM action or resource scope is introduced relative to those recovered definitions. JSON indentation differs from CloudTrail serialization; semantic hashes in [manifest.json](manifest.json) bind the documents. Raw CloudTrail envelopes and credential material are not included.

CreatePolicy will produce a **new policy ID and default v1** containing the reviewed document; it will not resurrect deleted policy versions or require CreatePolicyVersion/SetDefaultPolicyVersion. Metadata lookups still found the three policies absent. If any exact policy name exists at execution time, stop and compare ownership/document; never overwrite it automatically.

## Three CreatePolicy targets

| Policy name, root path `/` | Expected ARN | Actions | Compact characters |
| --- | --- | ---: | ---: |
| cnp-cert-eks-workload-boundary | `arn:aws:iam::341936017254:policy/cnp-cert-eks-workload-boundary` | 138 | 5023 |
| cnp-cert-app-workload-boundary | `arn:aws:iam::341936017254:policy/cnp-cert-app-workload-boundary` | 15 | 1736 |
| cnp-cert-management-workload-boundary | `arn:aws:iam::341936017254:policy/cnp-cert-management-workload-boundary` | 34 | 2796 |

The approval targets only `iam:CreatePolicy` and creation-time `iam:TagPolicy` for those three exact names/path/ARNs, with the exact document hashes and Project/Environment/Owner/Purpose tags in the manifest. No new user policy, access key, trust relaxation or AdministratorAccess attachment is proposed. The existing caller currently has AdministratorAccess; the workload boundaries remain separate ceilings. [IAM boundaries limit identity grants and do not grant permissions themselves](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html).

All actions are enumerated: **no `*`, `service:*` or `Describe*` Action pattern**. `Resource: "*"` remains in recovered statements and must not be hidden as a least-privilege claim. In particular, the historical EKS ceiling is a union covering seven roles; existing identity policies still supply their individual grants and conditions. Some broad mutation resources in that ceiling are historical compatibility choices, not a claim that AWS requires all of them to be unscoped. Narrowing that existing ceiling is a separate hardening decision, outside this restoration. IAM's [6144-character managed-policy limit](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html) is checked locally.

## What the ceilings permit

**EKS: seven existing source roles.** Cluster role; API and worker node roles; CNI and EBS CSI IRSA roles; Load Balancer Controller; Cluster Autoscaler. The 138-action set exactly equals the observed versions of the five AWS-managed policies declared by `infra/modules/eks/main.tf`, plus the repository's LBC policy and Autoscaler actions. The manifest records each observed version, action inventory and policy-document hash. Managed-policy changes must not be auto-accepted later.

- EC2 networking/storage reads and CNI/EBS/legacy cluster operations; ECR image pulls and the existing upstream-cache import capability; EKS cluster/nodegroup reads; existing Pod Identity role capability from AmazonEKSWorkerNodePolicy.
- ALB/controller and legacy ELB operations, Autoscaler reads/scaling. Autoscaler's role policy still restricts mutation to the cluster's two ownership tags.
- `iam:CreateServiceLinkedRole` is in a separate statement limited to the account's `elasticloadbalancing.amazonaws.com` service-role path and exact `iam:AWSServiceName`. It does not permit arbitrary role creation or PassRole.
- Optional ACM, Cognito DescribeUserPoolClient, WAF and Shield actions originate in the existing upstream LBC policy. Recovery does not create or configure those products, and this session does not use them. Legacy optional capabilities remain an explicit residual limitation of restoring the existing cap.

**App: five existing IRSA roles.** KEDA, Shipment, Tracking, External Secrets and CloudWatch:

- Shipment: ReceiveMessage/DeleteMessage/GetQueueAttributes/ChangeMessageVisibility on the **exact shipment queue**, and Decrypt on same-account/us-east-1 keys tagged `Module=event-encryption`; its identity grant selects the actual new key ARN.
- Tracking: PutEvents on the exact project event bus.
- KEDA: its identity grant permits only GetQueueAttributes; the shared boundary does not give it Shipment's consumer permissions.
- ESO: GetSecretValue/DescribeSecret for `cloud-native-platform/dev/runtime/*` and exactly the two current authorizer secret-name prefixes, including the AWS ARN suffix. No legacy-name or other-project prefix is retained.
- CloudWatch: CreateLogStream/PutLogEvents/DescribeLogStreams for this cluster's Container Insights groups; DescribeLogGroups, DescribeVolumes, DescribeTags and PutMetricData remain resource-wide telemetry capabilities. All six app statements require `aws:RequestedRegion=us-east-1`.

**Management: EC2 management and JWT authorizer roles.** The unchanged cap contains SSM/ec2messages/ssmmessages agent operations, three log-write actions for the exact authorizer log group, GetSecretValue for the two authorizer prefixes, DescribeCluster for this EKS cluster, and cluster-addons S3 reads. Existing management-principal-conditioned deploy-artifact version reads and receipt read/write statements are preserved. They are latent compatibility permissions; this block does not create the private-CD stack, enable delivery or exercise those paths. No unrelated S3 prefix or master database secret is added.

The exact action/resource lists are the three standalone JSON files. The local decision helper intentionally models only their StringEquals/StringLike conditions; it is not an AWS authorization engine. It does not establish SCPs, session policies, resource policies, trust, Kubernetes RBAC or database access.

## Other security changes during reconstruction

The three ceilings are prerequisites outside the 17 Terraform stacks. After their separately approved creation, unchanged Terraform source creates/attaches the normal project roles, policies, instance profiles, OIDC provider and exact service-account trusts. It associates these ceilings through role PermissionsBoundary fields; no existing unrelated principal is modified. Cluster creation retains the existing bootstrap-creator administration setting for the operator; Management's EKS access entry stays `platform:deployer:apps`, without cluster-admin. Namespace-scoped application/deployer RBAC, controller ownership and SSM/private TLS transit remain unchanged.

The exact stack scope is `vpc`, `nat`, `s3`, `ecr`, `event-encryption`, `sqs`, `eventbridge`, `eks`, `api-gateway-authorizer-secrets`, `runtime-secrets`, `api-gateway-authorizer`, `iam`, `apigateway-core`, `management`, `rds`, `observability` and `apigateway-integration`. `private-cd` remains unapplied. Fresh plans determine the actual resource count and generated identifiers; the historical 190-resource count is not reused as a new deployment count.

The three existing NAT SSM roles have **no permissions boundary in current source** and use AmazonSSMManagedInstanceCore. This is an existing limitation, not silently solved by restoring these three ceilings. Read-only GetRole confirmed the six shared service-linked roles for Amazon EKS, EKS Nodegroup, Auto Scaling, Elastic Load Balancing, RDS and EC2 Spot already exist. No first-time shared-role creation is presently planned; they are not project-owned teardown targets. If fresh checks find one missing, stop to review that exact shared-service dependency. Do not grant the workload boundary generic CreateServiceLinkedRole to handle it.

No need to recreate the historical temporary certification executors or attach their old operator policies to the caller: the authorized profile already has its observed operator permissions. Any actual denial from an SCP/permission change is a specific stop condition, not authorization to add grants. Management instance IDs, OIDC issuer/ARNs, SG IDs, key ARNs and EKS generation are newly bound from reviewed outputs. Old private-CD instance bindings and executor checkpoints are neither updated nor reused.

## KMS and credential decisions grouped now

Read-only project-tagged KMS discovery found two historical event-encryption keys PendingDeletion, scheduled for 13 November 2026 00:35:34 UTC and 13 November 2026 16:52:54 UTC. The exact alias `alias/cloud-native-platform-dev-events` has no current match. The proposal creates **one fresh project event-encryption key and that alias through existing Terraform source**. It does not cancel deletion, enable, decrypt with or reuse either old key. If fresh state/plans unexpectedly reference an old key or the alias is no longer free, stop rather than reactivate anything.

The existing dedicated key policy's account-root IAM-delegation statement (`kms:*`) and EventBridge GenerateDataKey/Decrypt service statement are unchanged source, scoped to that key. They are not new wildcard actions in the three IAM proposals. RDS/EBS/Secrets use the existing AWS-managed/default encryption configuration; no second custom runtime key is required by current source. The session cost model already reserved two active custom keys, so one new active key fits that allowance. [KMS does not charge key storage while scheduled for deletion](https://aws.amazon.com/kms/pricing/); PendingDeletion is still not physical absence.

Fresh runtime credentials **are** required because the runtime/secret containers were retired: six scoped database passwords, internal trust, synthetic bootstrap-admin password, JWT signing secret and gateway trust secret. Existing bootstrap initialization generates them randomly in memory and writes their initial Secrets Manager versions, never files/subprocess arguments/output. RDS creates/manages its new master password/secret. Preserve runtime/migrator separation; the existing private operator bootstrap may read the managed master secret in memory to create those scoped database identities. None of these values was generated or read during preparation.

Use a synthetic seed identity such as `eks-validation-admin+<run-id>@example.invalid` for `BOOTSTRAP_ADMIN_EMAIL`, supplied in the private operator environment. There is no email delivery or Cognito user to create. Synthetic accounts A/B and the fixture's single-user role/activity transitions remain within the reviewed Auth schema. **No new AWS access key, IAM user, AWS profile, Cognito configuration, real user or external SQL database is needed.**

## Local validation and retirement

```text
python -B scripts/validation/validate_current_profile_iam.py
python -B -m unittest discover -s scripts/validation -p test_current_profile_iam.py
```

Validation checks policy grammar, finite actions, size, exact targets/account/path, LF/canonical hashes, EKS declared-grant coverage, app inline-action coverage, current ESO paths, region conditions and exact management equivalence. Negative tests reject wildcard/alternative grammar, modified documents, wrong-account targets, generic role creation/PassRole, key/secret recovery, wrong queue/bus/region/tag and unrelated secrets/artifacts. This is local validation, not an Access Analyzer or live IAM simulation result. Protected infrastructure files, construction pins, journal/checkpoint algorithms and executor permissions remain unchanged.

Retire runtime through the existing fresh guarded COST_DOWN plan; restore Auth selectors and remove only owned probes first. Export evidence, purge synthetic RDS data/backups as explicitly approved, remove runtime images/artifacts/logs, schedule the new key's deletion and retain the existing state backend. Preserve the two old KMS deletion schedules.

**Explicit additional retention proposal:** keep only these three tagged boundary policies dormant after runtime retirement, with owner `platform-team`, documents/hashes versioned here and no surviving project-role boundary references. IAM has [no additional service charge](https://aws.amazon.com/iam/faqs/). This retention was proposed because the now-archived executor lacked an external-boundary DeletePolicy operation. Record this KEEP decision in the current [manual cleanup](../lab-cleanup.md) inventory. Do not claim a full IAM purge or remove the policies without reviewing their ownership and references. Future deletion requires a separate exact-ARN, association-free reviewed operation; no such deletion is authorized here.

The proposed single confirmation covers: these exact three CreatePolicy documents/tags; 17-stack reconstruction with unchanged source security relationships and a fresh KMS key; fresh in-memory application credential initialization; sequential .NET image build/scan/publication/deploy; three finite probe Jobs/ConfigMap; synthetic fixture transitions and CAS-guarded Auth outage/restoration; at most 30 minutes acceptance; **USD 8/six hours** as the spending/time envelope; evidence export; guarded synthetic-data retirement; and retention of the existing backend plus the three dormant boundaries. At hour four stop new tests and begin cleanup. The envelope is not an AWS-enforced hard cap; do not leave billable runtime overnight. No hosting, Private CD stack/delivery, GitHub push/merge or unrelated project is included.

## KEEP-only teardown decision

The approved current-profile session retains exactly the three boundary policies above and their observed policy-version children. The planner's `operatorBoundaries` category accepts only `KEEP`, an accountable owner, a deadline or explicit indefinite retention, and `resourceIds` containing exactly the three policy ARNs in this manifest. Versions inherit retention only through their observed exact policy parent. No IAM delete adapter or ownership promotion is added. Unknown unrelated resources, ambiguous/replaced identities, state-managed boundary policies, missing parent observations and incomplete discovery still block planning. FULL_PURGE cannot retain these policies.

This category does not classify other projects as owned. Review exact external identities separately through the existing prior-manifest mechanism; Terraform/project identity and owned-parent evidence continue to override exclusions. Generate fresh inventories, code fingerprints, plan hashes and approvals after this source change. Preserve the existing backend and confirm no surviving project-role boundary references after runtime retirement.
