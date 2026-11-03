# ADR-005 - Current account authorization behind API Gateway

Status: Accepted and implemented, 16 October 2026, including the two explicitly approved protected NetworkPolicy/cache changes. The [24 October acceptance](../operations/eks-acceptance-2026-10-24.md) adds scoped live authorization, TTL0 and CNI enforcement evidence; that environment is now retired. Earlier dated local-only statements below record their original checkpoint. See [hosting design](../architecture/frontend-hosting-decision.md) and [Private CD boundary](004-private-cd.md).

## Decision and scope

Shipment and Tracking require the existing gateway-attested user ID and constant-time proxy-secret verification **and** the original bearer. They call Auth's private `/auth/me` on every protected request, require the returned ID to match the attested GUID, require an active account and construct email/role claims only from the current profile. Gateway snapshot roles cannot retain removed Admin privileges. Auth remains responsible for JWT signature, issuer, audience, lifetime and account lookup; no signing key is distributed to either service.

The profile request has one eight-second deadline including response-body reads, a 16 KiB actual response limit, bounded profile fields and an 8 KiB Authorization-header limit. Redirects, cookies, environment HTTP proxies, retries and profile caching are disabled. Outbound requests contain the bearer and constructed JSON/cache headers, never incoming identity/internal headers or browser cookies. Caller cancellation propagates. Profile bodies, bearer values and upstream exception details are not returned or logged by these handlers; factory HTTP header logging is fully redacted.

Production and other non-Development environments use only `http://auth-service.apps.svc.cluster.local:8080/auth/me`. This is the existing private HTTP trust model, without a new TLS/mTLS claim. `AuthProfile:BaseUrl` cannot select another production origin. Development permits only the existing loopback Auth addresses or `http://cnp-local-ui-auth:8080`; these are operator configuration, never request-derived URLs.

Missing/forged/ambiguous gateway headers or bearer are rejected before contacting Auth. Auth 401 and deletion-race 404 become generic 401; Auth 403 or an inactive returned profile become 403. Mismatched identity becomes 401. Transport failure, timeout, redirects, unexpected status/MIME and malformed/oversized profiles become generic 503. Successfully authenticated users without the current policy's role receive 403. The legacy unsigned Development bearer-passthrough flag cannot bypass these checks. Internal service-secret authentication, ownership queries, Auth's refresh rotation, JWT format and event contracts are unchanged.

Shipment/Tracking also enforce a 16 KiB mutation-body limit against both declared and streamed bytes, with an eight-second read deadline, returning 413/408 before application code. Their responses have `Cache-Control: no-store`. The loopback proxy now forwards the original bearer alongside its constructed identity so the new backend check works; it still strips browser identity/internal headers and performs its own Auth check. This transitional extra Auth call is deliberate. There is no UI, asset, hosting, session-storage or BFF change.

## Local configuration

No Helm configuration is needed to choose the fixed production Auth origin. For source-mode LOCAL API, the default Development Auth origin is `http://127.0.0.1:8080`. A future rebuild of the already-supported local image fixture requires `AuthProfile__BaseUrl=http://cnp-local-ui-auth:8080` in the launcher's inherited process environment. Existing old images do not contain this implementation. Production-mode Docker fixtures need the fixed private DNS name as an isolated network alias; their historical results do not validate this change. Do not recreate fixtures, use a public gateway origin or change DNS on a live cluster as a shortcut.

## Exact NetworkPolicy change - implemented locally

The platform owns network policies; the app deployer must not gain permission to edit them. The implemented source change adds two directed runtime edges: Shipment to Auth TCP/8080 and Tracking to Auth TCP/8080, in namespace `apps`. Existing DNS, database, AWS egress and Tracking-to-Shipment rules are unchanged. This egress item appears only inside the Shipment/Tracking runtime-boundary policies:

```yaml
- to:
    - namespaceSelector:
        matchLabels: {kubernetes.io/metadata.name: apps}
      podSelector:
        matchLabels:
          app.kubernetes.io/name: auth-service
          platform.cloud-native.io/workload: runtime
  ports: [{protocol: TCP, port: 8080}]
```

Auth's runtime-boundary policy contains explicit reciprocal ingress items with the same namespace selector, runtime label and port, selecting `shipment-service` and `tracking-service` separately. Do not grant a namespace-wide destination, all ports, migration pods or Internet access. Existing ALB/private-subnet ingress is not broadened or redesigned. The new selectors do not imply that all prior ingress paths were removed.

The now-archived `scripts/operations/teardown_readonly/safety.py:baseline_guard` accepted exactly the two approved SHA256/LF source hashes below. At that revision its algorithm, baseline identity, other pins and rejection of untracked/unrelated construction were unchanged. Its archived regression tests included both paths in the exact-pin matrix and rejected unrelated source drift, stale implementation plans and approval reuse. Executor policies/versions, identities, checkpoints and journals were unchanged in that historical approval. New source fingerprints require fresh future operational plans; source review is not an AWS mutation approval.

The gateway authorizer result TTL now defaults to **0** in source, and dev inputs do not override it. The REQUEST authorizer and Authorization identity source remain intact. A future AWS apply will stop reusing allow/deny results and increase Lambda invocations for protected requests. JWT validation still runs on every invocation; the separate 300-second Secrets Manager value cache is unchanged. This does not implement CloudFront cache/routing or change CORS. No gateway resource was modified, and live enforcement remains unverified.

## Exact approved source delta

The user approved this exact patch after reviewing its scope. **It is applied to local files only**, with the two matching entries added to the construction guard. Hashes retain the existing SHA256/LF normalization convention. No old plan/checkpoint/journal is changed. Helm 4.2.2 rendered all three policies; exact object comparison and negative mutations verify the two added TCP/8080 edges, reciprocal ingress and all prior fields. This is source/render validation, not EKS enforcement certification.

| Source | Before SHA256 (LF) | Approved/current SHA256 (LF) |
| --- | --- | --- |
| `k8s/charts/platform-bootstrap/templates/network.yaml` | `3ba1272138f230a9072f54df7ed07dcdb687e466074ba0200f542a16d63e3a69` | `bc76075935fe481a0917aa7a71f602da6dd39cb1bd1a8b26498445bb6836db20` |
| `infra/modules/apigateway-core/variables.tf` | `04089019097bf9d3dc2f01ddf2653ea4ac4095496518968edc7d2e449328045d` | `094dfeedc6464760c93445d1fb325365b5582d9a1477fd3731fb98f51d8430d7` |

```diff
--- a/k8s/charts/platform-bootstrap/templates/network.yaml
+++ b/k8s/charts/platform-bootstrap/templates/network.yaml
@@ -30,6 +30,18 @@
               platform.cloud-native.io/workload: runtime
       ports: [{protocol: TCP, port: 8080}]
 {{- end }}
+{{- if eq $service "auth" }}
+{{- range $caller := list "shipment" "tracking" }}
+    - from:
+        - namespaceSelector:
+            matchLabels: {kubernetes.io/metadata.name: apps}
+          podSelector:
+            matchLabels:
+              app.kubernetes.io/name: {{ $caller }}-service
+              platform.cloud-native.io/workload: runtime
+      ports: [{protocol: TCP, port: 8080}]
+{{- end }}
+{{- end }}
   egress:
     - to:
         - namespaceSelector:
@@ -51,6 +63,16 @@
               - {{ . | quote }}
 {{- end }}
       ports: [{protocol: TCP, port: 443}]
+{{- if or (eq $service "shipment") (eq $service "tracking") }}
+    - to:
+        - namespaceSelector:
+            matchLabels: {kubernetes.io/metadata.name: apps}
+          podSelector:
+            matchLabels:
+              app.kubernetes.io/name: auth-service
+              platform.cloud-native.io/workload: runtime
+      ports: [{protocol: TCP, port: 8080}]
+{{- end }}
 {{- if eq $service "tracking" }}
     - to:
         - namespaceSelector:
--- a/infra/modules/apigateway-core/variables.tf
+++ b/infra/modules/apigateway-core/variables.tf
@@ -112,5 +112,5 @@
 variable "jwt_authorizer_result_ttl_in_seconds" {
   description = "Authorizer cache TTL in seconds."
   type        = number
-  default     = 60
+  default     = 0
 }
```

## Acceptance and evidence boundary

Offline tests use actual ASP.NET authentication/authorization middleware and an in-memory Auth HTTP adapter. They cover current claims, Admin-role removal using the same bearer, inactive/deleted accounts, Auth rejection/outage, ID mismatch, malformed profiles, duplicate/forged headers, bounded streamed responses/bodies, deadline and cancellation, generic errors and no-store. Existing Tracking Admin endpoint tests retain their application-boundary assertions using an explicit Auth adapter. No AWS, database server, container or new package is required for these focused tests.

Initial backend verification, before completing the protected-source changes, used Linux SDK 10.0.402 and the existing dependency cache: **81 Shipment tests, 89 Tracking tests and 14 proxy tests passed**, with zero failures or skips. The 46 new authorization cases run independently in each backend service. Documentation validation passed 207 local links/anchors; current-tree secret scan, whitespace checks and the unchanged construction baseline guard passed. These results used no Docker, package/image downloads or AWS API calls. Raw TRX/logs remain ignored under `.validation-results/auth-equivalence/`. No hosted CI was triggered.

The fake-adapter tests alone do not certify real JWT/database behavior. The subsequent isolated HTTP gate below tests those paths against real Auth/PostgreSQL with synthetic accounts; it does not certify production DNS, EKS NetworkPolicy or API Gateway forwarding. Cloud validation, production-account behavior, traffic latency/load and deployment/rollback remain pending. The previous 89 frontend tests and 23 Chrome checks describe integrated V2.1, not this new backend revision.

This closes the local authorization-source block; it does not start hosting implementation or authorize deployment. S3 private hosting, CloudFront OAC, same-origin uncached API, memory-only JWT without BFF and a separate portfolio lifecycle remain the later roadmap. Domain/publication, retention and AWS account/budget decisions remain open.


## Protected-source completion and real HTTP gate

[Network/cache contract checks](../../scripts/validation/validate_current_profile.py) run against actual rendered Helm and parsed HCL. R6 now checks the exact policy rules/selectors rather than merely allowing a port number. Negative cases reject namespace-wide/all-namespace peers, migration targets, extra destinations/ports, Auth lateral egress, missing reciprocal ingress, lost internal lookup, broader database egress and extra policies. Cache cases reject TTL 60, nonzero dev overrides, hardcoded TTL and missing TTL wiring. The reviewed source pins do not approve any of those variants.

The [explicit isolated HTTP gate](../../scripts/validation/current_profile_http_gate.py) requires `--run-isolated --dotnet <SDK-10.0.403-path>`. It checks free disk/ports and a cached PostgreSQL 15.18 image, uses one uniquely labelled 256 MiB container with tmpfs data and no persistent volume, then starts source APIs on loopback in Development. AWS workers are disabled; inherited AWS settings/profiles are removed and only synthetic credentials are supplied. No package restore, image build/pull or AWS request is performed. Cleanup verifies the run label before removing only its own container and stopping its own child processes. Private logs contain no returned bearer/password payloads; reports contain test names/statuses only.

The final gate passed **29 HTTP assertions**: register/login, actual Auth JWT checks, persisted shipment ownership and cross-user 404s, preserved internal Tracking-to-Shipment lookup, forged proxy headers and identity mismatch, removed Admin role with the same token, account deactivation/deletion, invalid signature, signed expired JWT, Auth outage returning 503 in both backends, and recovery without stale Admin authority. The fixture cleanup was confirmed. It uses a synthetic local database owner and plain loopback HTTP; it is not production TLS/role separation or cloud certification.

Focused verification for this completion: **27 network/cache/guard/R6/fixture-safety tests**, **52 edge/artifact-boundary tests**, **10 authorizer tests**, and the repeated **81 Shipment + 89 Tracking tests**, all passing with no skips. The cache/guard subset also passed 22 tests under Windows Python 3.13. Linux Helm/contracts used available Python 3.14.4 with the pinned cached HCL parser; hosted CI still pins Python 3.13. No runtime/toolchain pin was changed. Documentation, current-tree secret scan, Terraform formatting and the baseline guard are checked separately. Evidence remains ignored under `.validation-results/auth-equivalence/protected/` on both hosts.

No deployer permissions, IAM/RBAC actions, application-bundle membership, chart-template hashes, Private CD 1.4.0 contracts, migration history or teardown approvals were changed. The static hosting/release stages remain future work. EKS policy enforcement and API Gateway's actual zero-cache behavior need an authorized cloud session; no such result is claimed here.

Cloud execution preparation and its finite acceptance/cost/retirement proposal are in [the bounded AWS validation plan](../operations/current-profile-aws-validation.md). This does not authorize deployment.
