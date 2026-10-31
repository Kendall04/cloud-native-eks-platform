# Current-profile authorization: bounded AWS validation

Preparation only, 16 October 2026. Source prerequisite: `e7a7035fe17db55a6774a5cfc4704786f15880f3` and [ADR-005](../adr/005-current-profile-authorization.md). No deployment, image publication, fault injection or AWS mutation is authorized by this document. Hosting, domain decisions, frontend changes and Private CD certification are outside this block.

> Historical package: the 16 October observations, USD 8 model and six-hour window below are preserved for provenance. They are expired and do not authorize the next cycle. Use the [21 October reconciliation](../results.md) and [fresh manifest/budget/TTL requirements](teardown.md#proposed-lifecycle-classification) before requesting any future mutation. Current cloud certification remains pending.

## Observed starting point

Read-only CLI calls using **only `cnp-cert-dev`, us-east-1**, confirmed the expected account `341936017254` and principal `cnp-cert-admin`. The principal currently has AdministratorAccess attached and no user permissions boundary; that is observed metadata, not a reason to grant broader workload/deployer permissions. Recheck STS before any future operation and stop on mismatch. Never try another profile.

The exact EKS cluster `logistics-platform-dev`, RDS instance `cloud-native-platform-dev-postgres`, three ECR repositories and project-tagged VPC were absent. The expected API name returned no match. The existing owner-checked state bucket and ACTIVE lock table remain. These checks did not read state bodies, kubeconfig or secret payloads. Absence of these exact resources does not establish account-wide absence or release retained secret/KMS names for reuse.

NAT AMI `ami-03c3da4cfa8e8943a` is available, x86_64, with an 8 GiB root; PostgreSQL 15.18 is available. The Amazon-owned EKS node image `amazon-eks-node-al2023-x86_64-standard-1.35-v20261003` is available as `ami-06ee11fb2e882f9d5`. Exact advertised addon pins include VPC CNI `v1.23.2-eksbuild.1`, CoreDNS `v1.14.7-eksbuild.11`, kube-proxy `v1.35.3-eksbuild.49`, EBS CSI `v1.66.0-eksbuild.1` and CloudWatch `v6.2.0-eksbuild.1`. A project-prefix secret metadata listing including planned deletions returned no matches. Refresh availability/quotas and scoped bindings before apply; these observations are not future capacity guarantees. Do not substitute latest pins, recover old secrets or cancel KMS deletion without review.

**Reconstruction dependency prepared:** IAM GetPolicy returned NoSuchEntity for all three existing source references `arn:aws:iam::341936017254:policy/cnp-cert-{eks,app,management}-workload-boundary`. This is missing infrastructure, not an access-denied result. Subsequent read-only CloudTrail recovery located the EKS creation document and app's later default version; the latter already contains the current secret paths. [The three exact JSON proposals and IAM handoff](current-profile-iam/README.md) now include provenance, hashes, local validation, residual scopes and creation targets, with management semantically identical to its versioned source. They are review-only documents outside protected construction paths. No wildcard Action, role grant, source pin or IAM policy was added/changed in AWS. Apply still requires grouped approval to create the three exact policies and reconstruct runtime; the missing-definition preparation blocker is closed.

Windows and Linux were clean at the prerequisite SHA. Cached `cnp-ci/{auth,shipment,tracking}:dotnet10` images all identify revision `d6261c73eb4b902e1042c097d55eb92d66ee0620`; they cannot validate the new middleware. The VM has about 7.2 GiB free and an unrelated `windrose-sql` container. Do not prune, rebuild all images concurrently or touch that container. No builds/pulls were performed during observation.

## SSH diagnosis and minimal remedy

The restricted shell runs as `codexsandboxoffline`. OpenSSH resolves its home as `C:\WINDOWS`, misses the user's SSH config/known_hosts and resolves `codex-vm` differently. It fails before authentication. This is an execution-identity/configuration problem, not evidence of a rotated host key.

Run the existing SSH alias through the supported user-context sandbox escalation. It reads `C:\Users\PC\.ssh\config`, selects `kendall@192.168.92.128` and `id_ed25519_codex_vm`. With `StrictHostKeyChecking=yes`, the presented ED25519 key `SHA256:OU0g95u6sku0ROJv4ZJ5hIBZTjlm5thKXBGOk21bM0g` matches existing known_hosts line 34. No key was accepted, removed or rewritten. The same context resolves the existing AWS profile; the restricted context incorrectly reports it missing. Do not copy private keys/credentials or disable verification.

## Smallest supported reconstruction

Use the existing operator bootstrap and its dependency gates, not an alternate architecture. Its 15 core stacks plus observability and API integration make **17 runtime stacks** for this block. `environment.py` does not consume private-CD outputs; phase 3 accepts operator-built digest overlays. The eighteenth, private-CD stack, is unnecessary for these tests and should remain unapplied. If a real dependency contradicts this during plan review, stop and update scope before apply.

Retain the existing private EKS/ALB/RDS/management topology, three NAT instances, two On-Demand API nodes and one Spot worker, their encrypted disks, IRSA/ESO, messaging and controller ownership. These are existing dependency requirements, not new availability engineering. No NAT gateway, VPC endpoint, Cognito, CloudFront, domain, public cluster endpoint, new IAM role or permanent probe service is needed.

1. Confirm source and toolchain; acquire a fresh read-only inventory and fresh Terraform plans. Verify backend ownership, no active locks/writers, exact resource generations, pins and quotas. Recreate exact operator policy/resource bindings through their existing reviewed process; old instance IDs and old teardown approvals are invalid.
2. After grouped mutation approval, run existing bootstrap phases 0/1 and platform phase 2 with `AWS_PROFILE=cnp-cert-dev`, `AWS_REGION=us-east-1`. No GitHub workflow needs enabling. Phase 1 remains interactive; it must not silently reuse stale saved plans.
3. Build the three .NET 10 service images from one clean committed preparation revision, **sequentially**, using their existing pinned Dockerfiles, locked restore and `SOURCE_COMMIT`. Scan them using the repository's existing contract, publish only to the three project ECR repositories and deploy immutable digests through bootstrap phase 3 `--images <reviewed-overlay>`. Use fresh image metadata; old cached binaries and historical .NET 8 artifacts are unsuitable. Initial base-image/cache/disk availability is a preflight requirement; use another explicitly approved builder if 7.2 GiB is insufficient, never reclaim someone else's Docker storage.
4. Complete ALB discovery and API integration phases 4/5/6. Preserve the required healthy targets, private endpoint, CA validation and SSM operator transit. Phase 6 proves infrastructure wiring only.
5. Run the finite acceptance below, restore the deliberate outage, export evidence, then retire runtime through the existing guarded teardown.

## Prepared tools and offline commands

`scripts/validation/current_profile_cloud.py` uses the standard library. `observe` performs only fixed metadata reads, verifies STS before resource reads, fixes the sole profile/account/region, removes inherited AWS environment credentials/endpoints, and distinguishes explicit NotFound from incomplete/denied discovery. It never retrieves secret values or state bodies.

```powershell
python -B scripts/validation/current_profile_cloud.py observe
python -B -m unittest discover -s scripts/validation -p test_current_profile_cloud.py
python -B scripts/validation/current_profile_cloud.py manifest --run-id <24-lowercase-hex-run-id>
```

Manifest generation only prints JSON. It creates a proposed ConfigMap plus three finite Jobs in `apps`, using the already reviewed SDK image digest from the Auth Dockerfile. No new ECR repository is necessary. Jobs compile the package-free TCP probe from the ConfigMap using a feed-free NuGet.Config in a memory-backed temporary directory. They need no AWS credentials, Kubernetes token, privileged container, host networking, Service, NetworkPolicy or new RBAC. They use non-root/read-only roots, resource limits, no retries and a 180-second active deadline. SDK image acquisition by EKS and creating these four temporary objects are future approved actions, not performed here.

Probe Pods carry the same name/runtime policy selectors, but **omit `app.kubernetes.io/instance`**, so production Services cannot select them. Keep the generated object names, UID/ownerReferences and unique run label. Collect Job logs and Pod metadata, then delete only those exact run-owned objects with UID preconditions; no wildcard cleanup or automatic TTL deletion obscuring evidence.

## Finite acceptance: at most 30 minutes after readiness

Before probes, capture actual NetworkPolicies, aws-node configuration/readiness, selected Pod addresses, ready EndpointSlices and PolicyEndpoint associations. Standard CNI mode can initially allow traffic; the probe waits 60 seconds, but a delay alone does not prove binding. Require binding evidence and ready targets before accepting results. Do not edit PolicyEndpoint resources. Controller-owned Jobs follow [AWS's supported ownerReferences guidance](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html).

| Origin | Destination TCP/8080 | Required result, three samples |
| --- | --- | --- |
| Shipment | Auth | Connected |
| Tracking | Auth | Connected |
| Tracking | Shipment | Connected; preserves internal lookup |
| Shipment | Tracking | Timeout with DNS resolved |
| Auth | Shipment | Timeout with DNS resolved |
| Auth | Tracking | Timeout with DNS resolved |

DNS failure, connection refused, missing endpoints or an unbound policy are **inconclusive/fail**, never evidence of denial. Confirm Tracking's ready listener through a successful gateway lookup and all targets through readiness/ALB evidence. Existing private-subnet ingress remains broad: this matrix establishes selected runtime egress, not a new claim that all other namespaces/migration Pods are denied Auth ingress.

Use synthetic account A, ordinary account B and an independent bootstrap administrator; create one shipment owned by A. Use Auth's existing JWT/PostgreSQL model, no Cognito. Grant A Admin only through a reviewed, parameterized, single-user transaction using the existing scoped Auth database maintenance identity, then obtain **one** access token. No public role-management endpoint exists. Removing only A's `auth."AspNetUserRoles"` Admin membership requires the same scoped transaction and verification; do not add an API endpoint, change grants or update unrelated users. The existing private Admin disable route can deactivate A. Re-enabling A for outage/recovery requires the corresponding reviewed single-user maintenance transaction.

`http-phase` refuses execution without `--run-http`. Each invocation checks the sole AWS account, exact API name, actual REQUEST authorizer **TTL integer 0**, Authorization identity source and CUSTOM route associations before sending any HTTP. It performs three samples of the phase's requests, with a 12-second per-request timeout, no redirects or environment HTTP proxy. It records only status, no-store, gateway request ID, timestamp and a local SHA256 token fingerprint. It never reads response bodies or writes raw bearers. The empty Admin POST is deliberately invalid and must reach model validation without creating an event.

| Phase | GET shipments | GET A's tracking | POST empty admin tracking event |
| --- | --- | --- | --- |
| baseline, A currently Admin | 200 | 200 | 400 |
| revoked, same token | 200 | 200 | 403 |
| disabled, same token | 401 | 401 | 401 |
| outage, A re-enabled, Auth endpoints empty | 503 | 503 | Not sent |
| restored, same token, Admin still removed | 200 | 200 | 403 |

Keep the same token throughout, within its 60-minute lifetime. Store a private input JSON containing only `token` and `trackingPath` (`/tracking/by-shipment/<owned-shipment-guid>`) outside Git and shell history. After deployment approval only:

```text
python -B scripts/validation/current_profile_cloud.py http-phase --run-http --api-id <actual-id> --phase baseline --private-input <private-json>
```

Repeat for the four remaining named phases after the reviewed fixture transitions. Also verify B gets 404 for A's shipment/tracking and anonymous/forged-header requests fail; preserve request IDs without tokens. Actual TTL metadata is required because fresh backend roles alone cannot prove authorizer caching is off. AWS describes this [authorizer cache boundary](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-lambda-authorizer.html).

For the short outage, avoid fighting HPA: save Auth Service UID/resourceVersion and exact selector; apply an atomic JSON patch testing those values and changing the selector to a unique run-only label matching no Pods. Confirm zero ready Auth endpoints, run outage checks, then restore with UID/current-selector test preconditions in a finally/recovery procedure and prove ready endpoints returned. Do not scale competing controllers, delete HPA or edit DNS. Selector mutation and restoration are explicitly included in the future approval package. If restoration fails, stop further tests and restore service before retirement; no blind patch over concurrent changes.

Aggregate the three JSON probe records and five HTTP receipts in private files. `evaluate --network <json-array> --http <json-array> --run-id <id>` rejects missing samples/phases, unexpected allows, stale Admin behavior, token changes, cacheable responses and missing gateway IDs. It intentionally does **not** certify cloud deployment: a reviewer must bind raw receipts to actual Pod/Job UIDs, CNI bindings, target readiness, actual deployed digests/TTL/routes, restored Service selectors and teardown evidence. No self-reported boolean can replace those observations.

Stop after the first unexpected authorization/allow result; preserve evidence and diagnose once within the timebox. No endless reruns, load tests, broad resilience campaign, frontend certification or production SLA claims.

## Cost and duration proposal, not spending authorization

Rates checked 16 October 2026, us-east-1, USD before taxes/credits. AWS Price List API returned EC2 t3.micro **0.0104/h**, t3.large **0.0832/h**, RDS PostgreSQL Single-AZ db.t4g.micro **0.016/h**, and RDS gp3 **0.115/GB-month**. Use 730 hours/month for this estimate and price the Spot worker at the On-Demand rate conservatively.

| Item | Assumption | USD/hour |
| --- | --- | ---: |
| [EKS standard support](https://aws.amazon.com/eks/pricing/) | 1 cluster | 0.1000 |
| [EC2](https://aws.amazon.com/ec2/pricing/on-demand/) | 3 t3.large nodes, 3 NAT + 1 management t3.micro | 0.2912 |
| [Public IPv4](https://aws.amazon.com/vpc/pricing/) | 3 NAT EIPs; ALB/RDS/management private | 0.0150 |
| [ALB](https://aws.amazon.com/elasticloadbalancing/pricing/) | base + allowance of 1 LCU | 0.0305 |
| [EBS gp3](https://aws.amazon.com/ebs/pricing/) | 150 GiB nodes + 24 NAT + 8 management, 0.08/GB-month | 0.0200 |
| [RDS](https://aws.amazon.com/rds/postgresql/pricing/) | db.t4g.micro + 20 GiB gp3 | 0.0192 |
| [Secrets](https://aws.amazon.com/secrets-manager/pricing/) | 8 runtime + 2 authorizer + 1 RDS, 0.40/secret-month | 0.0060 |
| [KMS](https://aws.amazon.com/kms/pricing/) | allowance of 2 active customer keys, 1/key-month | 0.0027 |
| **Modeled base** | no free allowances deducted | **0.4846** |

Six runtime hours including teardown model about **USD 2.91** base. Reserve **USD 1.50** for logs/metrics, registry/artifact storage, API/Lambda/SQS/EventBridge/KMS/secret requests and transfer; **USD 1.50** for runtime/retirement variability; and **USD 1.00** for short retained evidence/storage. Propose an **EKS-specific USD 8 envelope for one session**, not the separate ECS or GitHub budgets. These variable reserves are planning allowances, not measured usage or quoted caps. Pre-existing retained backend charges, taxes and unrelated labs are excluded.

Target duration: 60-120 minutes reconstruction/images, 30 minutes acceptance, 45-90 minutes retirement; reserve up to six hours total from first paid runtime creation. Do not start if there is insufficient time to retire. At hour four, stop new tests/provisioning and begin retirement. If node count exceeds three, unexpected resources appear, forecast exceeds USD 8, a pin is unavailable or the deadline is threatened, stop expanding scope and continue safe cleanup. An AWS Budget alarm is delayed and is not a hard spending cap. T3/RDS CPU-credit surplus, log volume, extra LCUs and delayed retirement can exceed this estimate; this block does not intentionally generate load or leave runtime overnight.

## Restoration, evidence and retirement

First restore Auth's selector/endpoints and remove only run-owned probes/ConfigMap with recorded UID checks. Export sanitized revision/digest/tool, NetworkPolicy/CNI binding, API TTL/routes, request ID/status, fixture transition, restoration and cost observations. Keep bearer inputs, kubeconfig, SQL connection material, raw logs and state private.

For current retirement use [lab cleanup](lab-cleanup.md), selecting exact native identities, retained owners and a newly reviewed saved Terraform plan. Preserve management/private access until controller cleanup completes. Prepare RDS protection only when deleting that DB; review its data/backup disposition explicitly. This historical package does not authorize a new run or reuse old executor approvals.

## Single approval package before mutations

Approve together, only after reviewing the exact [IAM documents/manifest](current-profile-iam/manifest.json) and fresh plans: three CreatePolicy targets/tags with unchanged recovered ceilings; the 17 existing runtime stacks and source role/trust associations; a fresh event-encryption key/alias without reactivating either old key; fresh in-memory application/DB credentials and synthetic bootstrap email; sequential build/scan/publication of three current .NET 10 images and digest deployment; three run-labelled Jobs plus source ConfigMap; synthetic account/shipment fixture and scoped single-user role/activity transitions; brief CAS-guarded Auth Service selector outage/restoration; the bounded acceptance session; USD 8/six-hour EKS envelope; evidence export; and fresh guarded retirement including synthetic database loss while keeping the existing backend plus three dormant boundaries. No new AWS access key, GitHub push/merge, delivery enablement, hosting or other project is included.

## Approved execution checkpoint

The approved attempt created the three matching dormant boundary policies, then paused before runtime creation on a reproducible Windows provider mTLS failure and missing Linux profile authentication. See [the execution checkpoint](current-profile-aws-validation.md) for timestamps, unchanged scope and the human-controlled handoff. No live acceptance result is claimed.
