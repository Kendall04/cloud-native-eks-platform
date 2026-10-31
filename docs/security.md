# Security and reliability boundaries

**Evidence boundary:** controls below describe source contracts; the [28–29 October cycle](operations/eks-cycle-2026-10-29.md) and [results](results.md) identify demonstrated behavior. Runtime was retired after that cycle. Earlier assessments below remain dated evidence, not new approval, current scans or automatic renewal of security exceptions.

[Architecture](architecture/current-platform.md) · [Evidence and limitations](results.md) · [Secrets/database](operations/secrets-database.md)

| Boundary | Implemented control | Practical limit |
| --- | --- | --- |
| Kubernetes control plane | Private-only endpoint, IAM access entries and scoped RBAC | Operator network access and account bootstrap remain prerequisites |
| Public requests | HTTPS API Gateway, explicit routes, Lambda HS256 issuer/audience/expiry validation | Public registration/login still need application input/rate controls; no compliance claim |
| Trusted identity | Gateway overwrites headers; backend proxy secret and ownership/Admin checks | Internal HTTP/shared-secret trust, not mTLS or universal zero trust |
| Workload AWS access | Separate IRSA for publisher, consumer, KEDA and controllers; permissions boundaries | Effective policy scope and exact resource bindings must be reviewed after replacement |
| Database | Private RDS, SG-source ingress, VerifyFull TLS, distinct runtime/migration users | One shared Single-AZ DB instance, schema isolation rather than separate clusters |
| Secret handling | Secrets Manager sources, ESO synchronization, version-gated DB bootstrap | Env secrets require rollout; authorizer cache affects rotation propagation |
| Storage | Encrypted RDS and encrypted gp3 node roots; event CMK for queue/DLQs | Encryption is not proof of authorization correctness or data recovery |
| Kubernetes workload | Non-root containers, dropped capabilities, seccomp, no privilege escalation; proposed read-only roots with bounded scratch | Hardening requires a reviewed Private CD contract update before integration; namespace deployer can access Helm release Secrets |
| NetworkPolicy | VPC CNI policies select runtime pods, limit DB/DNS/internal HTTP and public HTTPS | Standard startup window; broad HTTPS egress; unselected/host-network pods not universally isolated |
| Delivery | OIDC, versioned hashed artifacts, fixed SSM executor, allowlisted Kubernetes kinds | Executor is privileged within apps; not an untrusted tenant sandbox |
| Cleanup | Exact inventory/plan/approval, persisted intent, dependency/residual barriers | Helm has no release-wide UID CAS; external actors still require an exclusive operator window |

The event CMK is shared by source and both failure queues. EventBridge has a service key-policy grant; queue policies independently restrict SendMessage to the intended rule. The service grant is broader than one rule. Tracking only publishes to the bus; Shipment gets queue/decrypt access; KEDA reads metrics without message decryption. See [ADR-001](adr/001-event-encryption.md).

## Reliability mechanisms

Tracking atomically commits events/outbox. Dispatcher leases, retry state and stable IDs survive restarts; Shipment row locking, inbox and per-aggregate sequences protect effects under duplicates/reordering. This is at-least-once delivery with idempotent processing, not exactly-once transport. Separate delivery/processing DLQs and retained outbox rows support reviewed recovery.

Auth/Tracking CPU HPAs (2–4), Shipment KEDA (2–6), Cluster Autoscaler, startup/readiness/liveness probes, PDB maxUnavailable 1 and soft topology spread address selected load/disruption conditions. PDBs govern voluntary eviction; they do not stop every crash or AZ failure. Soft spread does not force replicas into all AZs. A single NAT ASG replacement restored its EIP and route in 178 seconds; this is not a failover SLA or proof of post-replacement private egress. Single-AZ RDS remains a central availability limit.

CloudWatch includes structured JSON logs, EMF application/outbox metrics, managed observability, a dashboard and alarms. Alarm actions/human delivery are configuration-dependent. There is no demonstrated complete distributed tracing/SLO platform or production on-call service.

## Validation boundary

Current-tree secret scanning recognizes common AWS/GitHub tokens, JWT literals, private-key material and non-placeholder sensitive appsettings. It reports locations, not values. It is not a full Git-history audit or a guarantee against arbitrary unknown secret formats. ECR BASIC scan promotion rejects HIGH/CRITICAL or unavailable findings, but does not certify every dependency or the future patch posture.

[Results](results.md) identifies live observations separately from local contract tests and untested scenarios. No PCI, SOC 2, security certification, SLA, guaranteed HA or measured general-purpose RTO/RPO is claimed.

## Historical dependency assessment

The [per-exception evidence](evidence/security-remediation.json) records all 83 original exceptions, their scope, package/resource, original rationale, classification, compatibility risk and removal condition. The comparison uses Trivy 0.71.2, the same vulnerability database updated at `2026-10-15T01:13:01Z`, and the same check-bundle digest. Counts below cover one source scan and three final-image scans; repeated lockfile/deps.json/image appearances are separate occurrences.

| Measurement | Before | After |
| --- | ---: | ---: |
| LOW occurrences | 92 | 92 |
| MEDIUM occurrences | 91 | 63 |
| HIGH occurrences | 78 | 21 |
| CRITICAL occurrences | 6 | 6 |
| Unique scoped exceptions | 83 | 26 |

Removed 57 exceptions, added none, and kept the original 12 January 2027 expiry. Six distinct CVE identifiers disappeared from reports: CVE-2024-21319, CVE-2024-30105, CVE-2024-32655, CVE-2024-43483, CVE-2024-43485 and CVE-2025-6965. This is not six newly demonstrated exploitable runtime flaws: the count includes test graphs and obsolete lockfile entries. In particular, System.Text.Json 8.0.0 disappeared from NuGet locks; the final images already used shared runtime 8.0.32 before remediation.

At that historical remediation checkpoint, ASP.NET Core/EF packages used 8.0.32, the PostgreSQL provider 8.0.11 resolves Npgsql 8.0.6, memory caching resolves 8.0.1, and IdentityModel resolves 7.7.3. Shipment/Tracking tests explicitly use SQLitePCLRaw bundle 2.1.14; its native SQLite reports 3.54.0. The older report's empty `FixedVersion` for SQLite did not establish that upstream had no fix. Restores remain locked. SDK/global.json then used 8.0.426 and the build image uses its verified Jammy digest; the runtime digest remains unchanged. Patching the SDK alone would not update packaged application libraries or replace the runtime image.

At the dependency-remediation checkpoint, 26 exceptions covered 27 HIGH/CRITICAL configuration occurrences, including one repeated scanner result. Thirteen required compatibility work, eleven network/RBAC/ownership decisions, and two were scoped applicability cases. That historical comparison is preserved; the reviewed configuration hardening is recorded below.

Each .NET 8 runtime image at that checkpoint reported four LOW and three MEDIUM OS-package findings: GCC runtime packages, ICU, glibc and zlib. The pinned chiseled base is already the verified .NET 8.0.32 image; the scanner reports no fixed package versions for these findings. Track vendor fixes and refresh the verified base digest when available. No OS finding is hidden by the baseline. Python dependency scans report no vulnerabilities with this database. Absence of findings does not establish general safety.

### Build-stage SDK: separate assessment and residual risk

An additional scan found that SDK 8.0.419 carried runtime 8.0.25 and stale tooling. It was updated to the verified latest .NET 8 SDK 8.0.426, using Jammy to match the final runtime's Ubuntu family. The full SDK report changes from 260 HIGH/19 CRITICAL to 16 HIGH/0 CRITICAL; .NET-component occurrences change from 133 HIGH/2 CRITICAL to 16 HIGH/0 CRITICAL. OS advisory feeds differ between the previous Debian image and Jammy, so the whole-image reduction is not a count of CVEs demonstrably fixed by a package patch.

The 16 remaining HIGH occurrences are reported without filtering in the evidence. Six are MSBuild CVE-2025-26646 applicability cases: [Microsoft's advisory](https://github.com/dotnet/msbuild/security/advisories/GHSA-h4j7-5rxr-p4wc) identifies 17.11.4 and SDKs through 8.0.409, whereas this SDK bundles 17.11.48/17.11.69. Ten concern old Pkcs/Xml packages bundled inside `dotnet-format`. That tool is not invoked by this CI, but its presence remains supply-chain debt. Replacing DLLs inside the vendor SDK is not a supported remediation; obtain upstream servicing or review the local .NET 10 comparison below.

These SDK results are outside the original 83-exception adoption scope and the source/final-image CI gate. No SDK exceptions were introduced and no scanner finding was converted into an accepted baseline entry. The existing CI must not be described as scanning every build-stage tool. Ephemeral PR runners have read-only repository permissions and no AWS identity; that limits exposure without eliminating the underlying tooling issue.

Raw reports, policy decisions, CycloneDX 1.7 SBOM and tool/image metadata are retained as local validation output and PR Actions artifacts. Local builds explicitly record dirty-tree status; GitHub artifacts identify the committed PR revision. SBOM image IDs identify local builds, not unpublished ECR digests.

## Residual hardening proposal and integration boundary

This section preserves an earlier proposal; it is not a new implementation authorization or current scan.

The `residualHardening` section of the [evidence file](evidence/security-remediation.json) compares the PR #54 checkpoint with the reviewed hardening tree using the same Trivy DB and check bundle. Source/config occurrences change from 161 to 135: HIGH 21 → 7, CRITICAL 6 → 3. Unique exceptions change from 26 to 9 (six HIGH, three CRITICAL); 17 were removed after configuration correction and local checks, none added. Ten remaining HIGH/CRITICAL occurrences share nine fingerprints. The separate 16 SDK HIGH results are outside this inventory. All remaining expiries stay at 12 January 2027.

| Change | Evidence and limit |
| --- | --- |
| RDS removes general outbound access | No database-initiated connections/extensions are declared. HCL checks forbid alternate/inline egress and additional DB groups. [Stateful SG replies do not require outbound rules](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html), and the [pinned provider removes default egress on creation](https://github.com/hashicorp/terraform-provider-aws/blob/v5.100.0/website/docs/r/security_group.html.markdown#basic-usage). Verify actual rules and TLS connectivity after reconstruction. |
| Public subnet auto-addressing defaults off | Each NAT instance still explicitly requests a public address and owns its EIP association. Topology and routes are preserved. Per-AZ bootstrap/replacement/EIP/egress remain live checks. |
| KEDA 2.20.2 drops arbitrary custom scale targets | Official `enabledCustomScaledRefKinds: false` retains built-in Deployment/StatefulSet and HPA permissions. Real local authorization and cron/external-metric HPA scaling 1 → 2 passed. SQS and IRSA were not exercised. |
| KEDA Secrets restricted to its namespace | The application namespace is no longer watched for Secrets. The upstream certificate Role still grants get/list/watch/create/update in `kube-system`; this is not a claim of exact-name or cluster-wide Secret denial. Local allow/deny checks confirmed that boundary. |
| Application and migration roots become read-only | Only a 64Mi memory `emptyDir` at `/tmp` is writable, with group 1654; the CA remains read-only. Three production-mode migrations/readiness checks passed against local PostgreSQL 15.18 with VerifyFull TLS. Auth register/login/profile/refresh passed. AWS consumers/outbox were disabled only in the local fixture. |
| Addon contexts become explicit | ESO controller/webhook/cert-controller reached Ready locally with non-root pod contexts. Autoscaler additionally uses the chart's documented UID 65534, read-only root, no privilege escalation and dropped capabilities. Autoscaler AWS discovery/scale and metrics-server EKS kubelet TLS/readiness remain unverified. |

The disposable kind 0.33.0 cluster used Kubernetes 1.35.8, a version in [KEDA 2.20's tested minor range](https://keda.sh/docs/2.20/operate/cluster/). Twenty runtime/RBAC checks passed: six deployments Ready, effective permission boundaries, ESO Fake-provider reconciliation, certificate regeneration, KEDA external metrics/HPA scaling and rejection of a competing ScaledObject. Only this test fixture excluded the AWS controllers and metrics-server; production charts keep all addons enabled. The cluster was removed after testing.

Three CRITICAL exceptions remain: Management HTTPS egress for changing AWS/package endpoints through NAT, ESO certificate-controller webhook writes, and KEDA admission/APIService CA reconciliation. ESO already limits update/patch to named webhooks and CRDs and its own Secret. Local certificate regeneration and negative permission tests support preserving those duties. KEDA's upstream minimal role remains broader for CA injection; no supported exact-name value was found. Neither permission is called a false positive merely because it is upstream.

The HIGH exceptions retain EKS default-encryption applicability, Auth's numeric refresh-duration false positive, and exact network-resource rules for autoscaler, LBC and the `apps`-only deployer Role. Management DNS/PostgreSQL rules stay separate from TCP/443. DNS-name allowlists cannot be expressed in security groups and no complete stable free prefix list covers the existing HTTPS dependencies; no paid endpoints or new CMK were introduced.

**Protected contract review and controlled integration.** The follow-up task explicitly authorized the two changed template hashes and nine exact construction-source pins. The [old/new hashes and review evidence](evidence/security-remediation.json) are recorded under `protectedContractReview`; the SHA256/CRLF normalization algorithm is unchanged. No stack/resource identity, mutation operation, historical checkpoint, journal or approval was added or rewritten. Source review is not permission to destroy resources: changed implementation fingerprints invalidate old plans and their approvals.

The executor policy and manifest requirement advance from 1.3.0 to 1.4.0 because the scratch/read-only policy changes the installed contract. A future rebuilt host must install the matching policy; old bundles/hosts are not silently interchangeable. The bootstrap retains the 16 KiB EC2 user-data limit. Exact archive membership rejects unpinned CRDs or other chart files even when outer checksums are recomputed. Exact Pod/container contexts also prevent values from dropping `drop: ALL`, disabling seccomp or changing scratch mounts. Tests preserve the prior rejection of arbitrary templates, wrong pins, unknown construction, stale plans/approvals and manipulated journals. No live AWS behavior or general absence of bypasses is claimed.


| Verification boundary | Evidence / next checks |
| --- | --- |
| VERIFIED LOCALLY | 801 Python cases (one declared PostgreSQL skip covered separately), 158 .NET tests with PostgreSQL 15.18, 10 authorizer tests, 64 focused contracts including 46 R4 tests; prior disposable kind and read-only-container checks described above. |
| VERIFIED IN GITHUB ACTIONS | [PR #56](https://github.com/Kendall04/cloud-native-platform-eks/pull/56) and its recorded [34-job validated revision](https://github.com/Kendall04/cloud-native-platform-eks/actions/runs/38699102731). Integration requires fresh Validate on develop, its promotion PR and the resulting main. Inspect each exact run; local tests do not substitute for hosted checks. |
| REQUIRES LIVE AWS | NAT bootstrap/replacement/EIP and egress in every AZ (including previously untested A); RDS TLS/migration/runtime access without general egress; Management bootstrap/SSM; Private CD 1.4.0 rollout/rollback; KEDA/SQS/IRSA and HPA; Autoscaler/LBC/metrics-server; ESO AWS sync/certificate rotation; application/addon contexts and migration Jobs; the full guarded lifecycle/teardown. |

The final integration is tracked through PR #56 and the subsequent `develop` → `main` promotion. Historical pre-merge statuses in the evidence file describe their recorded revisions; they do not authorize future deployment or teardown. The lab remains offline.

## .NET maintenance boundary

The security hardening was integrated on .NET 8 before the separate runtime migration. Microsoft's [.NET support policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core) places .NET 8 end of support on 10 November 2026 and .NET 10 LTS end of support on 14 November 2028. The local migration below addresses that boundary; the historical AWS lifecycle remains a .NET 8 result.

The migration coordinates SDK, ASP.NET Core, EF Core and Npgsql without unrelated major upgrades to AWS SDK, Swashbuckle or xUnit. The Node.js authorizer and Python NAT handlers are unchanged. Local checks cover HTTP/event contracts, database compatibility, containers and security. Hosted Validate passed on the recorded PR revision; the later live deployment and rollback are recorded separately in the dated results.

## Local .NET 10 migration

The [migration evidence](evidence/dotnet10-migration.json) records SDK 10.0.402, ASP.NET Core/EF Core 10.0.13 and Npgsql 10.0.3, with no migration or snapshot changes. Using the same Trivy 0.71.2 database, each new Noble chiseled-extra application image reports **0 HIGH/CRITICAL**, two MEDIUM and one LOW OS-package findings. The source/configuration scan retains the same nine scoped exceptions, expiry 12 January 2027, and ten HIGH/CRITICAL occurrences. No new exception or suppression was added.

The full vendor SDK comparison is separate: 16 HIGH occurrences in SDK 8.0.426 versus four in SDK 10.0.402, with zero CRITICAL in both. The new SDK no longer reports the older MSBuild/dotnet-format occurrences. Its four remaining HIGH results are CVE-2026-84008 and CVE-2026-96958/96959/96960 in the bundled PowerShell 7.6.7 dependency graph (`System.Security.Cryptography.Pkcs`/`Xml` 10.0.10; fixed 10.0.13). These identifiers also occurred in the old SDK, in a different bundled tool. CI uses neither PowerShell nor those tooling paths for application builds. This limits exposure but does not remove the vulnerable bundled components; retain the raw assessment and track an upstream SDK/PowerShell servicing image. Do not edit vendor DLLs or convert SDK findings into application exceptions. The ordinary source/final-image security gate still does not scan every build-stage tool.

The recorded GitHub PR run also passed all 34 jobs. Its newer Trivy DB (15 October 2026, 07:10 UTC) reports the same source/image findings; a separate local SDK recheck with that DB still reports four HIGH. These checks do not certify AWS runtime behavior. The existing live-AWS compatibility checklist still applies to the next reconstruction, including .NET 10 health/readiness, existing data and migration compatibility, and rollout/rollback.
