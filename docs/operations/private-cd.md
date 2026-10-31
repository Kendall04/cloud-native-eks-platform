# Private CI/CD

[Deployment](deployment.md) · [Security](../security.md) · [Recorded delivery](../results.md#delivery-evidence)

GitHub-hosted runners use AWS APIs; they have no network path to the private EKS endpoint. A fixed executor on management performs the Kubernetes work. The workflow definitions retain their triggers in source, but all three AWS delivery workflows are currently disabled in GitHub.

## Triggers and artifact flow

```mermaid
sequenceDiagram
  participant GH as GitHub Actions
  participant IAM as IAM OIDC
  participant ECR as ECR
  participant S3 as Versioned S3
  participant Host as SSM / private management
  participant EKS as Private EKS
  participant API as API Gateway
  Note over GH: Manual Build (CI V2); historical v2.0.7 used push
  GH->>GH: Validate source and tests
  GH->>IAM: Assume publisher role
  GH->>GH: Build three service images
  GH->>ECR: Push immutable SHA images and resolve digests
  GH->>S3: Immutable image records
  Note over GH: Manual Create Release on main
  GH->>IAM: Assume publisher role for this workflow
  GH->>ECR: Verify digests and scan findings
  GH->>S3: Read versioned environment contract
  GH->>S3: Publish data-only bundle, VersionId, hash
  Note over GH: Manual Deploy on main / dev environment
  GH->>IAM: Assume orchestrator role
  GH->>Host: Fixed SSM document, exact artifact and revision
  Host->>S3: Verify artifact, hashes and replay state
  Host->>EKS: Apps-scoped Helm migrations and rollout
  Host->>EKS: Deployment / endpoint readiness
  Host->>API: Auth backend 400 and anonymous 401 smoke
  Host->>S3: Versioned receipt and active artifact marker
```

| Workflow | Trigger in source | Result |
| --- | --- | --- |
| `validate.yml` | PR to main/develop, push to main/develop, or reusable call | AWS-free tests, containers, Trivy/SBOM, Helm/IaC/workflow and secret checks |
| `build-sha-images.yml` | Manual dispatch on main/develop | Validation first; build/scan three images and publish immutable build records |
| `create-release.yml` | Manual dispatch on main | Reviewed `vMAJOR.MINOR.PATCH`, migration assertion, data-only artifact |
| `deploy-platform.yml` | Manual dispatch on main, `dev` environment | Exact artifact key/VersionId/hash, operation ID and expected revision |

A push now validates local images without publishing. AWS build/publication, release and deployment each require a separate manual dispatch once explicitly authorized and enabled. The recorded v2.0.7 build used the earlier push trigger. Environment reviewer/branch protection configuration is an operator setting, not guaranteed by the YAML alone. See [CI V2](../development.md#ci-v2) for local checks, adoption policy and artifact metadata.

## Identity and promotion

[Private-CD IAM](../../infra/modules/private-cd/main.tf) separates publisher and orchestrator roles. OIDC validates the audience and repository subjects: publisher refs are main/develop; deployment uses `environment:dev`. A permissions boundary further constrains each role. No long-lived AWS key is stored in a workflow.

Build records bind service, source commit, workflow run and ECR digest. Publication checks successful build-run identity, ECR digest consistency, the versioned operator environment snapshot and ECR BASIC scan findings. Missing/failed scan evidence or HIGH/CRITICAL findings block promotion. This is a promotion gate, not a complete application vulnerability assessment.

The bundle contains manifest, chart and resolved values with hashes; it carries data, not arbitrary shell/Python or raw secret values. Both runner and host validate it. The host allows only reviewed apps resources (Deployments, Services, ConfigMaps, Ingress, migration Jobs, PDBs, HPAs and ScaledObjects). RBAC, CRDs, service accounts, NetworkPolicies and ExternalSecrets remain platform-owned. Template hashes bind the executor's reviewed chart contract. The reviewed residual hardening requires executor policy 1.4.0 for its bounded memory scratch and read-only workload roots. Install the matching reviewed executor during a future authorized reconstruction; 1.3.0 bundles and hosts are deliberately incompatible. This source review does not update any running host or authorize AWS delivery.

## Configure a new environment

After bootstrap and final contract validation, export metadata with the operator identity:

```bash
python3 scripts/cd/export_environment.py --environment-file .generated/dev/environment.json --bucket <artifact-bucket>
```

This writes S3. Record the returned key, VersionId and SHA-256. Set repository/environment variables from fresh Terraform outputs:

| Variables | Source |
| --- | --- |
| `AWS_REGION`, `AWS_ACCOUNT_ID`, `ARTIFACT_BUCKET` | Chosen account/region and S3 output |
| `ARTIFACT_PUBLISHER_ROLE_ARN`, `DEPLOYMENT_ORCHESTRATOR_ROLE_ARN` | private-CD outputs |
| `ENVIRONMENT_CONTRACT_KEY`, `ENVIRONMENT_CONTRACT_VERSION`, `ENVIRONMENT_CONTRACT_SHA256` | Export receipt |
| `EKS_CLUSTER_NAME`, `PLATFORM_ALB_GROUP_NAME`, `ALB_FRONTEND_SECURITY_GROUP_ID`, `SHIPMENT_QUEUE_URL` | Final environment contract |
| `MANAGEMENT_INSTANCE_ID`, `SSM_DOCUMENT_NAME`, `SSM_DOCUMENT_VERSION`, `SSM_DOCUMENT_SHA256` | management/private-CD outputs |

Rebind the exact management target in effective IAM and GitHub variables after redeploy. A stale boundary can deny SendCommand even if workflow variables are correct. The final source commit contains this repair; do not restore old instance IDs.

Once authorized and enabled, run Build SHA Images for the reviewed commit; dispatch Create Release with the version and `previous-release-compatible` assertion; inspect its publication receipt; dispatch Deploy Platform with that exact receipt, a unique DeploymentId and current Helm revision (`0` for first install). These remain distinct operator decisions.

An alternative local `operator-deliver`/`operator-redeploy` path exists in [publish.py](../../scripts/cd/publish.py). It requires the dedicated temporary executor identity and records `OPERATOR_LOCAL`, never fabricated GitHub run evidence. It is not the default GitHub procedure and does not bypass artifact/scan/SSM contracts.

## Executor, smoke and rollback

### ALB pod readiness gates

The platform operator enables `elbv2.k8s.aws/pod-readiness-gate-inject=enabled` on namespace `apps` during bootstrap phase 2, before application rollouts. This namespace setting remains platform-owned; application bundles and the management executor do not modify it.

On 29 October 2026 the operator added this label to the running lab after checking LBC v2.14.0, the webhook and all three IP TargetGroupBindings. Server-side dry-runs using each real Service selector injected its corresponding `target-health.elbv2.k8s.aws/…` gate without persisting a Pod or changing Helm history.

The [single controlled v2.0.8 retry](https://github.com/Kendall04/cloud-native-platform-eks/actions/runs/40921100633) then completed successfully, moving Helm from revision 3 to 4 without rollback. A watch started before dispatch recorded all six new Pods waiting on their gates, ALB health for their exact IPs before gate True, and old Pod deletion only after replacement availability. The existing executor passed all three strict smoke gates; its code, pinned hashes and IAM were not updated for this test.

Injection applies only at Pod creation and requires a matching Service and existing IP TargetGroupBinding. A first installation without those bindings does not gain this guarantee merely from the namespace label. Existing Pods are not retrofitted. Before a delivery, verify injection with `kubectl create --dry-run=server -f <private-safe-pod-manifest> -o json`, then observe the new Pod IPs, their gate conditions and the corresponding ALB target identities during the authorized rollout. Counting healthy targets alone is insufficient. The strict Auth HTTP 400/ProblemDetails/request-ID smoke remains required.

### Deployment checks and recovery

The host checks account/cluster/private endpoint, artifact and chart hashes, image digest references against the manifest, fresh ESO reconciliation, DB bootstrap versions and expected Helm revision before mutation. The publisher verifies ECR digest consistency; the host does not independently query ECR or compare running pod image IDs. It uses Helm 4 rollback-on-failure, waits for jobs and records the attempted/active revisions.

Smoke has three distinct stages:

1. `KUBERNETES_READY`: ready Deployments/Service endpoints and Ingress address.
2. `AUTH_BACKEND_REACHABLE`: invalid empty refresh input returns Auth's expected 400 problem response and request ID.
3. `EDGE_ANONYMOUS_REJECTED`: anonymous `/shipments` returns 401.

This proves Auth edge routing and Kubernetes readiness, not a complete authenticated business journey. The functional tests in [results](../results.md) provide separate coverage.

A host lock and GitHub concurrency serialize deployment. Expected revision rejects stale requests. Same-ID completed replay returns its historical receipt without rerunning Helm or moving the active marker; a changed request under that ID is rejected. Interrupted RUNNING state requires observation and reconciliation. Runner timeout/cancellation does not prove that the host stopped.

Failed upgrade/smoke attempts recover the previous release where one exists, verify restored manifest/values and repeat smoke. The attempted deployment remains failed even if recovery succeeds. First install has no previous release. For manual rollback, submit the previous immutable artifact with a new operation ID and the current expected revision. Helm rollback never reverses PostgreSQL migrations; compatibility is a reviewed assertion. After event v2 activation, do not roll back to the old event-v1 application protocol.

Receipts record artifact/source identity, revisions, stages, bounded diagnostics and rollback results in versioned S3. Unknown outcomes remain unknown. The successful post-redeploy path was observed; the available final record does not establish live fault/replay coverage for every implemented safeguard. See [limitations](../results.md#limitations).


## Local IAM handoff: review only, 21 October 2026

The [exact review packet](private-cd-iam-proposal.json) closes the known policy-design gap using the existing module/operator path. It is **UNBOUND / NOT APPLIED / NOT AUTHORIZATION**, not a native root IAM policy, installation tool or permission simulation. Neither missing policy nor role is created here. The earlier [read-only preflight](../evidence/eks-readonly-preflight-20261021.json) observed both absent. USD25/8h and USD1/30d remain proposals; the owner selected B as a preparation preference only; hosting effects/cost still need approval.

**Separate actors.** `cnp-cert-dev` resolved to IAM user `cnp-cert-admin` for preflight, with AdministratorAccess and no observed user boundary. That is not the delivery identity. The existing [trust document](../../infra/operator-policies/cnp-cert-private-cd-executor-trust.json) names that observed user only as STS issuer, session name `cnp-private-cd-operator`; the proposed runtime principal is `arn:aws:sts::341936017254:assumed-role/cnp-cert-private-cd-executor/cnp-private-cd-operator`, maximum session 3600 seconds. Its identity grant plus the shared Private CD boundary restrict delivery. No AdministratorAccess, state/IAM/PassRole/EKS/secret/KMS/teardown rights go to that role. The issuer remains broadly privileged; this does not establish whole-environment least privilege or independent approval by itself. Issuance/renewal must use the normal separately approved human/tool path, with no new permanent key, cached credential handoff or broker. Session expiry never proves a submitted SSM job stopped.

**Existing references are not install-ready.** The historical boundary pins retired instance `i-01b740869f2c9104c`; `private-cd-apply.json` pins a different retired `i-031d7ef07d85316af`. The old boundary omits `operator-image-records/dev`, which `publish.py` actually uses. The apply reference mixes IAM/state/lock writes with delivery and lacks complete retirement rights. Do not attach it to the runtime operator or describe it as a create/destroy capability. Historical files and protected construction are unchanged by this proposal.

The packet contains two policy templates with **16 explicit action names each**, no wildcard Action. The shared workload ceiling preserves current publisher/orchestrator contracts and adds the missing operator-record namespace; role identity grants preserve their separation. The dedicated operator grant omits CI `image-records` and environment-contract publication/read, because `operator-deliver` consumes the reviewed local environment file. Exporting a versioned environment snapshot remains a separately reviewed platform-owner operation. The management host keeps its existing separate boundary, `platform-deploy` user and apps-only RBAC; no boundary/grant from this proposal replaces them.

| Runtime operator action group | Exact resource/condition contract |
| --- | --- |
| ECR token | `ecr:GetAuthorizationToken`, Resource `*`, `aws:RequestedRegion=us-east-1`; this API has no repository-level Resource. Image rights remain the next row |
| Three images | `ecr:BatchCheckLayerAvailability`, `InitiateLayerUpload`, `UploadLayerPart`, `CompleteLayerUpload`, `PutImage`, `BatchGetImage`, `GetDownloadUrlForLayer`, `DescribeImages`, `DescribeImageScanFindings`, each with the `ecr:` prefix; only `arn:aws:ecr:us-east-1:341936017254:repository/{auth-service,shipment-service,tracking-service}`. IAM grants repository writes, not proof of a reviewed tag/source; immutable tags, scan/build/artifact contracts remain required |
| Immutable publication | `s3:PutObject` only under exact artifact bucket `cloud-native-platform-341936017254-dev-us-east-1-artifacts`, `deploy-artifacts/dev/*` and `operator-image-records/dev/*`, with `StringEquals s3:if-none-match="*"`. The condition star is a literal HTTP precondition. No receipt writes, delete, bucket list or environment/CI-record write |
| Reads | `s3:GetObject`/`GetObjectVersion` only on those two namespaces plus `deployment-receipts/dev/*`. The shared ceiling additionally permits the source CI record/environment read namespaces; that ceiling grants no identity permission by itself. Object suffix wildcards retain the existing standing-contract choice for unknown commit/hash/operation keys, not an IAM-imposed requirement; exact per-operation keys can be reviewed once known. They do not authorize foreign buckets/environments |
| Fixed delivery | `ssm:SendCommand` must cover **both** `arn:aws:ssm:us-east-1:341936017254:document/cloud-native-platform-dev-deploy-apps` and the **fresh exact** management instance ARN. The template deliberately contains `${MANAGEMENT_INSTANCE_ID}`, not a wildcard or invented resource. Document version/hash and artifact/config/revision checks remain application contracts, not claims of IAM enforcement of those parameters |
| Observation/identity | `ssm:GetCommandInvocation` Resource `*` with region condition; its lack of resource-level scope means broader invocation-output visibility in that region, an explicit residual limitation. Existing `sts:GetCallerIdentity` Resource `*` is identity observation only, no AssumeRole grant. Neither wildcard grants shell/session/document-update APIs |

**Binding/install handoff, before any execution:** first obtain the actual management output matched to fresh DescribeInstances ID/LaunchTime, role/profile generation, account/region and normal owner state; match the fixed SSM body/version/hash and installed host executor 1.4.0. Substitute that exact instance in **both** templates, record final bytes/digests, then independently review the IAM effect. This cannot be finalized before those IDs exist. If either missing IAM name now exists, stop and compare ownership; no silent replacement/version update. The separate account owner may create the exact boundary v1 with the packet's tags, then create the exact operator role with that boundary, referenced trust and only the delivery inline policy. Capture PolicyId/RoleId. The packet enumerates `CreatePolicy/TagPolicy` and `CreateRole/TagRole/PutRolePolicy` plus exact-owner reads; CreateRole is constrained to the boundary ARN and project/environment request tags. No installation or new principal creation is authorized by this local packet.

**Prepare removal as well as creation.** The runtime operator cannot tear down infrastructure or alter its own IAM. Before creating the new role/policy, the responsible installation owner must accept their separate exact cleanup recipe in the packet. After the last delivery, stop new delivery, reconcile in-flight SSM/host execution and export receipts. Existing graph order remains applications before `private-cd`, and `private-cd` before management/S3/ECR. Terraform owns its two federated roles/inline policies, fixed document and the state-captured management inline artifact policy. Proposed removal rights are exact-role `GetRole/ListRolePolicies/GetRolePolicy/ListAttachedRolePolicies/ListInstanceProfilesForRole/DeleteRolePolicy/DeleteRole`, fixed-document describe/get/permission/tag reads plus `DeleteDocument`, and **only** `DeleteRolePolicy` on management for the state-captured artifact inline policy. IAM scopes inline operations to the role, so the exact policy-name limit is a saved-plan/owner invariant, not an IAM guarantee. Unexpected attachments, shares, policies or UNKNOWN execution block; no generic detach/unshare/force cleanup is proposed.

The operator role and workload boundary are **outside** that Terraform module and the existing three-policy KEEP-only parser. Do not extend that parser, hide a new retention or claim the current executor removes them. Their installation owner removes only the captured inline policy/RoleId after quiescence, and deletes the captured boundary PolicyId/v1 only after both federated roles and operator are absent, attachment/boundary counts zero and no additional version exists. Extra versions need fresh review, not default DeletePolicyVersion rights. The review packet lists these exact actions/resources. Completion needs fresh `NoSuchEntity`/complete scoped observations, not exit zero alone, and normal tool confirmations may still be required for the concrete future payload.

Resolve GitHub OIDC ownership before module apply: the existing variable supports referencing an existing shared provider. Preserve that provider without import/deletion. If creation by this module is chosen, capture its ARN/creation generation and require complete fresh trust-consumer review before owner deletion. Optional owner metadata enumeration `iam:ListOpenIDConnectProviders`/`ListRoles` needs Resource `*`; neither list API accepts the provider ARN as a resource-level filter. These are **not** operator grants or foreign-role deletion rights. Incomplete/denied coverage or a foreign trust consumer blocks that removal. The historical apply reference is not a complete installer/retirement policy.

### Retentions preserved without another blanket decision

| Existing disposition | Reason/cost and whether it blocks this cycle |
| --- | --- |
| Backend S3 versions/lock table | Preserve exact state lineage/recovery/journals. Version storage/requests remain billable and were not fully quantified; no zero-cost assertion. No active lock key was observed at preflight, not a future lock guarantee. Not a new retention decision; recheck owner/lock/state before effects |
| Ten active secrets and ESO role/inline policy | Preserve the already retained credentials/identities; approximately USD4/month for secrets plus requests, with source 30-day runtime/7-day authorizer deletion defaults if a separately authorized deletion is ever selected. One AWSCURRENT version each was observed without values. Not blocked by absence and no request to redefine/delete them. New DB/bootstrap use or versions need cycle consent; ESO trust must be normally rebound to the new OIDC generation without replacing/adopting the role blindly |
| Three EKS/app/management boundaries | Preserve observed exact v1 policy IDs/hashes. They are prerequisites, not newly missing policies. No separate role/policy storage charge is modeled; this is not a billing certification. The missing **fourth Private CD boundary/operator** is the actual IAM blocker addressed above |
| Three historical event CMKs | Preserve their PendingDeletion disposition and deadlines below; source event-encryption/SQS states were empty. No current CNP consumer was identified in those empty states, but global/cross-project dependency absence was not proved. They cannot serve the new cycle and must not be re-enabled, rescheduled or treated as new deletion targets |
| Shared `alias/aws/rds` / `alias/aws/secretsmanager` | Observed distinct shared key dependencies for the normal managed services. No deletion, policy change or old custom-event-key substitution; the Private CD artifact bucket source uses SSE-S3, so this delivery grant needs no KMS/secret action |

| Historical key suffix (account/region ARN in receipt) | Observed deletion deadline UTC | Dependency implication |
| --- | --- | --- |
| `0fdce1f0-418b-4463-b751-44e818ef475e` | 2026-11-13 00:35:34.974Z | Old event key; preserve pending, never bind new queues/artifacts to it |
| `e354ff52-7648-469e-8238-48fece53eb4a` | 2026-11-13 16:52:54.734Z | Old event key; same rule |
| `08bded46-3283-4561-a518-5afa836f1437` | 2026-11-19 17:47:21.003Z | Latest retired event key; same rule |

The receipt's USD1/key-month is an **active-key tariff**, not proof that these scheduled keys incur three active key-month charges. No revival/new usage or pending-key budget is requested; billing and physical deletion were not certified. The normal new `event-encryption` key/alias, its consumers and later deletion disposition must be separately approved for the new cycle. The retained app boundary is only a ceiling permitting `kms:Decrypt` on event-encryption-tagged keys; the live IAM source grants the future consumer the exact fresh `dependency.event_encryption.outputs.key_arn`. Do not confuse that ceiling/tag with an instruction to reuse any of these old keys. The missing IAM installation/removal handoff still needs concrete approval; hosting B is selected for local preparation, with no publication/spending approval; existing retentions stay preserved unless the owner explicitly asks to change one. No hosting code, AWS call or security setting changes in this increment.

Local validation: seven bounded grammar/source/fixture checks passed on Windows and on Linux over SSH, including 32 rejected operator requests (foreign/stale targets, other prefixes, missing publication preconditions, IAM/secret/KMS/state/teardown operations). Linux reused cached tools; its one older management-host contract file was staged only in ignored validation storage for exact source hashing. No provider, clone, installation, build or AWS read/effect occurred. This is not AWS IAM simulation, policy effectiveness or a successful runtime/retirement claim. Template hashes and the retained log hash are in the review packet.

## Publisher environment: offline build and Windows import

The bounded split is implemented in [image_oci.py](../../scripts/cd/image_oci.py) and [publish.py](../../scripts/cd/publish.py), with synthetic format/transport regressions. It has **not built or published a real image**. No Docker-config read, credential transfer, builder creation, new IAM grant or cloud staging bucket occurred. The Windows Docker-config denial remains in force; this path never invokes Windows Docker. Linux receives application bytes and the pure OCI helper only, not IAM policies or AWS credentials.

1. From a clean reviewed checkout, run `python scripts/cd/image_oci.py prepare --service auth --commit <HEAD> --output <private-source-manifest.json>` for each of auth/shipment/tracking. Capture the manifest SHA-256 and transfer only its tracked context files plus the helper over the existing SSH channel. The helper copies only listed, hash-matched, regular files into a temporary build context; unlisted files are excluded. A dirty/wrong checkout, missing Dockerfile, symlink or escaping path blocks preparation/build.
2. On Linux, `python image_oci.py build --source <manifest> --sha256 <manifest-sha256> --source-root <context-directory> --output <new-service.oci.tar> --builder <existing-local-builder> --builder-state <existing-buildx-metadata-directory>` uses an **already running local docker-container builder**. Inspection must show its Unix socket, running status and no insecure entitlements. The function uses an empty Docker config on tmpfs and an allowlisted environment without AWS/GitHub credentials; it neither creates nor bootstraps a builder. The Docker default driver cannot export OCI: see the [official exporter contract](https://docs.docker.com/build/exporters/oci-docker/). An unavailable/unqualified existing builder is a concrete prerequisite, not permission to install one or retry denied config access.
3. Return only the three OCI archives and their SHA-256 metadata once. Inputs are a JSON array of three objects with exact fields `service`, `archive` (Windows path), `sha256`. Archives must be single-image Linux/amd64 OCI with source commit, service and source-manifest labels. The importer streams and verifies the complete manifest/config/layer graph, compressed digests and uncompressed rootfs diff IDs. Each gzip layer must also parse as TAR with valid headers/member bodies and at least two terminating zero blocks; nonzero content after the archive is rejected. A second streaming gzip pass checks structure without extraction or a decompressed file. Layer member count is capped at 100,000, metadata payloads at 1 MiB and header nesting at 16; declared/expanded sizes retain the existing 2-GiB ceiling. Metadata limits apply before parser allocation or GNU sparse processing; absolute/traversing member paths, sparse/unsupported members and links escaping the image root reject. Standard in-image absolute/relative symlinks and hardlinks are parsed without following them or creating devices/files. The [TAR correction receipt](../evidence/eks-publisher-layer-tar-fix-local-20261022.json) records the demonstrated previous failure and Windows-only regressions. Missing/extra/duplicate blobs, links, external URLs, unsafe paths, hidden tar content, size limits, source/platform mismatch and changed archives reject before AWS identity calls. No extraction or second large image copy is needed. Actual image sizes/transfer volume remain unmeasured; reuse caches and stop if required space is unavailable.
4. On Windows, set the approved account/region/artifact-bucket environment and run `python scripts/cd/publish.py operator-import --image-inputs <private-inputs.json> --import-receipt <new-private-jsonl-outside-checkout> --expected-role-id <fresh-delivery-RoleId>`. All three archives must validate before the existing `cnp-cert-dev` profile is opened. STS must resolve the exact previously approved admin UserId, then assume only `cnp-cert-private-cd-executor` for 3600 seconds and verify its fresh RoleId/account/session. Temporary credentials stay in the Windows process, without files or environment exports. No alternate principal/fallback is supported.
5. Import is **not deployment**. With the role installed and fresh generation bound under the approved cycle, it can read exact ECR tags/blob availability/scans, upload missing config/layer blobs with `InitiateLayerUpload`, contiguous `UploadLayerPart` chunks using the returned 5–20 MiB part size (a shorter final part is allowed) and `CompleteLayerUpload`, and `PutImage` only for `auth-service`, `shipment-service`, `tracking-service` in 341936017254/us-east-1. It uses tag `operator-sha-<commit>`, verifies returned digests, and conditionally writes exactly three versioned `operator-image-records/dev/<commit>/<service>.json` objects in `cloud-native-platform-341936017254-dev-us-east-1-artifacts` **after** the unchanged complete-scan/HIGH-or-CRITICAL gate. Existing mismatched tags/records block. It does not create repositories, buckets, IAM, a registry token or SSM commands. It does not touch infrastructure, secrets, hosting or historical retention.
6. The separate existing `operator-deliver ... --expected-role-id <same-fresh-RoleId>` then reuses those immutable records/images without a Docker fallback, packages through the existing environment/chart contract and invokes the same fixed SSM path using the in-memory role session. Missing records/images stop before registry authentication. `operator-redeploy` accepts the same optional session binding and existing immutable receipt; CI defaults and GitHub run verification remain unchanged. Neither delivery nor redeployment was executed for this increment.

The source-manifest labels bind reviewed bytes to an **operator-controlled builder**, not a cryptographic build attestation or proof of reproducible output. Import records retain the existing five-field schema. Their numeric `buildRunId` is an archive-derived operator evidence ID, not a GitHub run. The separate operator namespace and `githubActionsVerified: false` receipt prevent CI adopting these records as verified Actions builds. Real .NET runtime/platform checks, image scanning and application tests remain future cycle gates.

The [AWS upload contract](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_UploadLayerPart.html) caps each part at 20 MiB; an unsupported returned part size stops after initiation for reconciliation. All new STS/ECR/S3 transport clients use a single attempt. The private receipt flushes intent/outcome metadata, digest/upload ID and confirmed S3 VersionId, never image bytes or credentials. A denial, ambiguous response, partial upload or timeout stops; uploaded blobs/images can remain without a record. Reconcile the last intent and actual target before any replay; do not change routes/principals to evade a denial. No automatic cleanup, replay, deployment or token refresh is added. Existing orchestrator read retries remain bounded; SendCommand remains single-attempt.

**Before real use:** bind the clean final source revision; confirm the existing local OCI-capable builder and disk/transfer capacity without denied config access; create/bind the already-approved delivery role/boundary and exact management target only through the cycle's normal reviewed plans; capture its actual RoleId and effective `sts:AssumeRole`/delivery rights. The split adds no grant. Fresh environment/capacity/cost/state/retirement gates still apply. There is no EKS resource or first-cost timestamp from this increment; USD25/8h and the protected USD15 reserve are unchanged, and the published hosting expiry is untouched.

### Publisher environment: separation proposal only

The prior design-only checkpoint is retained in [the KEEP receipt](../evidence/eks-retained-secrets-local-20261022.json). Its publisher limitation describes that earlier revision; the implementation and offline evidence above supersede only that limitation, not the historical denial or any cloud gate. See [the split validation receipt](../evidence/eks-publisher-split-local-20261022.json) for executed checks and remaining prerequisites.
