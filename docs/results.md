# Results and evidence

[Overview](../README.md) · [Architecture](architecture/current-platform.md) · [Security](security.md)

## Latest completed cycle: 28–30 October 2026

| Capability | Demonstrated scope |
| --- | --- |
| Application | Private EKS 1.35, three Ready nodes, six base service replicas, .NET 10 and PostgreSQL 15.18; real authentication, authorization and persisted shipments/tracking |
| Events | Two sequences correlated through Tracking outbox, EventBridge, SQS and Shipment inbox with persisted effects |
| Private CD | Manual Build → Release → Deploy; v2.0.8 reached Helm revision 4. A previous HTTP 504 smoke triggered verified automatic rollback |
| ALB convergence | Readiness Gates verified against the actual replacement pod IPs and healthy ALB targets |
| NAT replacement | Stable EIP and private route restored in 178 seconds; post-replacement private egress remained UNVERIFIED |
| Browser integration | Real CloudFront → API Gateway → EKS/PostgreSQL trial, followed by explicit AWS → DEMO return without silent data fallback |
| Retirement | Runtime cost-down completed 29 October at 20:50 Costa Rica, retaining protected RDS, its network, historical identities, evidence and independent hosting |

See the [dated closure](operations/eks-cycle-2026-10-29.md) and [sanitized observations](evidence/eks-portfolio-observations-20261029.json). These are evidence of specific tests, not continuous monitoring or general availability guarantees.

## Static publication: 30 October 2026

The final Logistics Platform Demo and five Archify diagrams were published as an explicit synthetic DEMO. Source: `fb8c0f36e07102d39562254c819b8c7d494dee70`; package SHA256: `e29381029c72eddcedec765deb61385f318d6a7d63af2697d0b78b318573818c`. Two independent builds produced identical packages. Publication verified twelve required S3 objects, with eleven conditionally created and one reused, before selecting the release through the existing routing function.

Public checks covered DEMO and Explorer, the selected build identity and JSON 503/no-store for `/api`, `/api/shipments` and `/api/auth/me`. The distribution retained one private S3 origin and no API forwarding. Original publication receipts, VersionIds and browser captures remain private; no fresh AWS observation is claimed by this documentation update. The earlier release remains retained for reviewed rollback.

## Retentions and outstanding limits

Hosting retention remains **21 November 2026 at 01:04 UTC**; publication does not renew it. RDS was retained stopped with protection/data/backups; its recorded automatic restart was due **5 November at 20:14:57 Costa Rica**. These are operational dates, not confirmation of a later resource state. Retained storage, secrets and artifacts can incur charges; the lab's budget model is not an invoice.

RDS is Single-AZ; observed A/A/C node placement is not a scheduling guarantee. NAT recovery did not prove uninterrupted egress or cross-AZ failover. Helm rollback does not undo PostgreSQL migrations. AWS-to-DEMO selection is not proof of rollback between different authenticated AWS frontend versions. Accessibility checks cover tested states, not complete WCAG conformance.

## Earlier evidence

Everything below describes an earlier revision and observation window. In particular, historical RDS deletion, absent hosting, pending validation and Build-on-push statements do not describe the final cycle or the current workflow definitions. Counts from different cycles must not be added together.

## Historical state: 24 October 2026

The [closed .NET 10 cycle](operations/eks-acceptance-2026-10-24.md) supersedes the current-state descriptions in the dated records below. Its [curated 27-task matrix](evidence/eks-acceptance-20261024.json) binds selected private receipt hashes: C2 direct29/gateway42, CNI18, C3 events53, C4 rollback/capacity23 and real web13 checks. These counts overlap scopes, not a unique summed test count. Original stopped attempts and the later CPU cooldown follow-up remain separate evidence.

Closure at **2026-10-24 07:33:53.884233 UTC** verifies39/39 stages,178 Terraform objects retired,3 separate temporary IAM objects absent,16 empty+2 retained readable states and no own active locks. Original ESO/ten secrets, twelve hosting objects and state/history were preserved. The single new key remains PendingDeletion30days; four historical schedules are unchanged. Foreign denied attributes remain NOT_VERIFIED: this is scoped EKS closure, not a global account purge.

The USD11.83 conservative model includes unspent allowances and contingency; the invoice is unknown. Public DEMO is restored and its API returns503/no-store. Hosting A/B/A release selection differs from Helm rollback and does not prove two different authenticated web-source releases or a continuous old browser tab across the transition. No new deployment is needed for remaining repository documentation, privacy review or hosted CI/Dependabot tasks.

## Historical snapshot: 21 October 2026

The latest retirement supersedes the 14 October snapshot below. At **20 October 18:11:26 UTC**, the closure recorded **325/326 cumulative targets absent or retired**, **39/39 stages complete**, and **18 readable Terraform states: 16 empty of managed objects and two with 12 managed objects retained**. Ten CNP secret identities were intentionally retained; managed-object counts are not secret counts. One KMS key remained pending within that plan, while three CNP keys were pending across the broader account. Pending deletion is not physical absence.

Fresh focused reads at **21 October 01:37:27-01:37:41 UTC**, using only `cnp-cert-dev` / account `341936017254` / `us-east-1` after STS verification, found zero EKS clusters, zero EC2 instances in pending/running/stopping/stopped/shutting-down states and zero RDS DB instances. Ten CNP secrets had no DeletedDate; three exact previously audited CMKs remained PendingDeletion, scheduled for 13 November 00:35:34.974 UTC, 13 November 16:52:54.734 UTC and 19 November 17:47:21.003 UTC. Backend S3 versioning remained Enabled. No secret values, state bodies or object contents were read. This was a focused refresh, not a new full-account audit.

The recent 01:06-01:12 UTC residual audit also established absence of ASG/EBS/own snapshots/NAT gateways/VPC endpoints/RDS backups in its `us-east-1` API coverage and surveyed justified categories in `us-east-2`. Those categories/regions were not repeated here; no universal regional/service coverage is claimed. Private source filenames, hashes, observation scope and [revision/capability limits](results.md) are retained in the [new evidence manifest](evidence/reconciliation-20261021.json).

Ten retained CNP secrets imply about **USD 4/month base**, before requests/taxes/credits and retained backend storage/requests; [AWS Secrets pricing](https://aws.amazon.com/secrets-manager/pricing/) was rechecked on 21 October. The preceding audit counted about 5.24 MB in 206 backend versions, not a fresh measurement. [AWS KMS pricing](https://aws.amazon.com/kms/pricing/) charges no key storage while deletion is scheduled; other retained resources can still cost money. The **USD 58.9025627945** Cost Explorer total for 1-20 October is estimated/incomplete historical whole-account spend, not EKS-only cost or a forecast. ECS ALB/EIP decisions belong to the other lab; its reported 01:24 UTC cleanup was not rechecked or performed by this review.

The current .NET 10 / frontend / Auth-profile / executor 1.4.0 revision still needs bounded cloud certification. The 14 October lifecycle used .NET 8. Hosting remains unimplemented/undeployed. No application suites were rerun for this documentation pass; [teardown lessons](operations/teardown.md#lessons-from-the-20-october-retirement) preserve the observed failures and limits.

## Local frontend increment: 21 October 2026

The [AWS-mode implementation and validation record](architecture/frontend-hosting-decision.md) adds the explicit static-client prerequisite from the hosting design. It uses the existing same-origin HTTP/session contracts with visible AWS labels, build-time configuration validation and no synthetic fallback. Its browser gate uses intercepted loopback-only responses; it proves no AWS, CDN, .NET runtime or Private CD behavior. Hosting and remaining release/versioned-asset work are still pending. This increment does not refresh the historical AWS observations above.

## Local static packaging increment: 21 October 2026

The [static packaging record](development/frontend-release.md) adds versioned presentation URLs and a reproducible local artifact with a closed public configuration/integrity manifest. Its evidence covers repeated builds, negative package validation and Chrome served from verified package contents. It does not establish publication, hosting, actual cache headers or remote promotion/rollback.

## Local certification baseline preparation: 21 October 2026

The [baseline review and finite acceptance](operations/eks-acceptance-2026-10-24.md) isolates the Management/EKS tombstone comparison repair from 77 unrelated dirty paths. Its local regressions do not certify the current cloud revision. Native-CNI admission, object-scope/retention review and independent execution authority remain pre-cycle gates; all live acceptance rows are PENDING. No historical source recovery, approval/window reuse, AWS call or RDS-pilot change occurred.

## Historical lifecycle: 14 October 2026

The platform completed deploy → functional tests → teardown → redeploy → functional tests → final teardown. The final machine-readable report finished at **2026-10-14 17:28:21 UTC** (11:28:21 in America/Costa_Rica, UTC-06:00). Both time zones give 14 October. The `20261013` filename is not the completion date.

## Evidence boundary

This page is a curated summary of private local reports inspected during documentation review. The [JSON summary](evidence/lifecycle-summary.json) records selected observations, source filenames and original SHA-256 hashes. That historical JSON omits account IDs, endpoints, instance/volume IDs, users and raw payloads. The new reconciliation names its authorized account and read scope without secret payloads. Private originals, recovery journals and state versions remain outside the repository. Hashes support comparison by an authorized holder; they are not independent public verification or a signature.

The implementation baseline reviewed here is `65e62dd73084943b16e46ff02a33afcdaed4c3f0`. The post-redeploy application delivery used `7768fcea12731da63e4fc83542c8b7c0771c7247`; the later commit repaired exact management-target IAM binding. Architecture descriptions follow source, not every historical intermediate configuration.

## Lifecycle observations

| Scope | Evidence-backed outcome | Interpretation |
| --- | --- | --- |
| First teardown | 190 Terraform resources retired; 18 empty states | Runtime removed before reconstruction |
| Redeploy | 18 stacks and 190 resources recreated; EKS 1.35 | One demonstrated reconstruction, not an arbitrary-account installer |
| Nodes/storage | 3/3 Ready across two managed groups; three encrypted 50 GiB gp3 roots | Observed node roots, not every account volume |
| Services | Auth 3, Shipment 2, Tracking 4 Ready before final cleanup | Point-in-time autoscaled replicas, not fixed desired capacity |
| Functional tests | Register/login/refresh/profile, shipment creation, tracking creation/timeline reads, anonymous/non-admin rejection, invalid/expired JWT and event propagation passed | Authenticated business integration against RDS, separate from CD smoke |
| Pod resilience | One deleted Auth pod's replacement reached Ready in 26.1 seconds | Single recovery sample, not an outage/RTO guarantee |
| Egress | DNS/HTTPS and matching NAT EIPs passed in B/C | A was NOT_TESTED because no nodes were there |
| Final teardown | 190 resources retired; 18 empty states, no locks and consistent backend checksums | Runtime absence verified at report time, backend intentionally retained |

The 14 October report records removal of EKS/nodes, management/NAT/EIPs, RDS/data/backups, EBS/snapshots, ALB/targets, ECR/images, API/authorizer, messaging, runtime S3, secrets/logs and project IAM runtime identities. Five temporary executors and 17 exclusive policies were removed; unrelated labs were preserved. The 14 October documentation pass did not repeat AWS discovery; the later focused metadata reads are scoped above.

## Delivery evidence

The final redeploy delivery is recorded as `v2.0.7`, Helm revision 2, with actual running image digests verified:

| Stage | Trigger | Historical run |
| --- | --- | --- |
| Build SHA Images | `push` | [Successful build](https://github.com/Kendall04/cloud-native-platform-eks/actions/runs/38595681871) |
| Create Release | `workflow_dispatch` | [Successful publication](https://github.com/Kendall04/cloud-native-platform-eks/actions/runs/38597648582) |
| Deploy Platform | `workflow_dispatch` | [Successful private delivery](https://github.com/Kendall04/cloud-native-platform-eks/actions/runs/38598641855) |

These links require repository access while GitHub remains private. The receipt records KUBERNETES_READY, AUTH_BACKEND_REACHABLE and EDGE_ANONYMOUS_REJECTED as PASS. Those smoke stages have a narrower scope than the functional business tests. Release/deploy were not automatically triggered by push.

Read-only GitHub inspection on 14 October 2026 confirmed all three delivery workflows `disabled_manually`, Validate active and repository visibility private. Definitions remain versioned for reconstruction; no workflow was reactivated during documentation work.

## Cost and retained resources

S3 state versions and the DynamoDB lock/checksum table were retained for evidence and future reconstruction. Two customer KMS keys were recorded PendingDeletion, scheduled for 12/13 November 2026; pending deletion is not physical absence. The dates are scheduled observations, not confirmation that deletion later occurred.

The delayed Cost Explorer total was approximately USD 12.38 **for the whole account, including other labs**. Exact project spend was not determinable. The report's USD 7.43 scenario and tiny backend-storage estimate are omitted as portfolio cost claims because they depend on capacity/time/pricing assumptions and exclude charges. Retained storage/requests may still accrue costs. No zero-bill assertion is made.

## Limitations

- This is a lab, not production, a compliance assessment or an SLA. Single-AZ RDS, one management host and EC2 NAT create explicit failure/capacity limits.
- NAT egress was tested with pods in B/C, not A. Subnets in three AZs do not prove workload placement or availability in all three.
- Resilience tests cover selected pod, rollout/drain and readiness scenarios. Sampling and one 26.1-second recovery do not establish zero downtime or generalized recovery guarantees.
- The earlier report records 45 idempotency/concurrency tests against disposable local PostgreSQL 17; functional integration used RDS 15.18. CI is configured for PostgreSQL 15.18. Do not describe the entire concurrency suite as an RDS load test.
- The successful private-CD path was exercised after redeploy. Replay, stale-revision and rollback controls are implemented/tested locally; the final evidence alone does not prove every live failure scenario.
- Exact project cost and eventual physical KMS deletion remain unconfirmed. The 21 October focused reads above refresh only their named scope; the historical application tests were not rerun.
- Reproduction needs recreated scoped operator policies, refreshed resource bindings, available pinned dependencies and deliberate workflow activation. It is not a fresh-account one-command deploy.
