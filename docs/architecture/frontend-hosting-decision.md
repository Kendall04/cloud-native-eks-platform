# Frontend hosting and secure API integration

[Architecture](current-platform.md) · [Frontend setup](../../frontend/README.md) · [Publication runbook](../operations/frontend-demo-promotion.md) · [Results](../results.md)

## Decision

Use the existing private S3 bucket and CloudFront distribution for immutable static releases. Hosting is independent of EKS and survives runtime cost-down within its separately approved retention. The final published edition is DEMO; the AWS edition and API forwarding were demonstrated during the 28–29 October trial and then withdrawn.

DEMO and AWS are **different builds**, not automatic availability detection. DEMO uses synthetic in-memory data. AWS calls same-origin `/api` and reports backend failures honestly; it never substitutes synthetic data.

| Option | Tradeoff | Decision |
| --- | --- | --- |
| Browser calls API Gateway directly | Requires absolute API configuration and reviewed cross-origin policy | Not needed for this client |
| CloudFront forwards same-origin `/api` | Reuses the existing API, client and static hosting; explicit API/cache controls | Selected for authorized AWS editions |
| New BFF | Adds session custody, permissions, runtime and failure paths | Not required; Auth already verifies current identity |

## Traffic and ownership

- **Static:** browser → HTTPS CloudFront → OAC-signed private S3. S3 serves files; it never forwards API traffic.
- **Authorized AWS edition only:** CloudFront → HTTPS API Gateway → VPC Link → HTTP internal ALB → HTTP private services. There is no end-to-end TLS or mTLS claim for internal HTTP hops.
- **DEMO:** API origin and ordered API behaviors are absent. The static router returns JSON 503/no-store for `/api` and `/api/*` without contacting a backend.

The hosting root is [independent Terraform](../../infra/portfolio/frontend-static/README.md), not one of the 18 runtime stacks. Its trusted state, recovered lineage, resource ownership and live function selection must be verified before changes. The original lineage was lost; it must not be invented or replaced during release selection.

## Authentication and trust

Public registration, login and refresh routes do not use the Lambda authorizer. Protected routes use the Lambda REQUEST authorizer to validate JWTs. Gateway integrations overwrite trusted identity headers. Shipment/Tracking verify that envelope and the original bearer against Auth's current profile, then apply user/role/ownership rules; Auth validates its own protected endpoints. See [ADR-005](../adr/005-current-profile-authorization.md).

CloudFront strips viewer `x-platform-*` headers and cookies from API requests. This is defense in depth, not authentication. API Gateway remains directly reachable; backend controls must hold without CloudFront. OAC protects S3, not the API. No signing key, proxy secret or AWS credential belongs in a static build or `VITE_*` variable.

The browser holds access tokens only in memory, omits cookies and discards refresh tokens. Reload/logout/expiry clears the session; 401 also clears it. A generic 403 is not automatically logout. There is no browser logout revocation endpoint or protection against a script using a token during an active session. Current-profile validation adds an explicit Auth/RDS availability dependency and fails closed.

## Routing, cache and browser policy

| Mode/path | Behavior |
| --- | --- |
| Static navigation | Allowlisted application routes select the active release's HTML; unknown paths must not receive a universal SPA fallback |
| Versioned assets | Exact immutable keys, MIME and content hashes; missing assets remain errors, never HTML |
| AWS `/api` and `/api/*` | Separate HTTPS API origin, exact prefix removal, CachingDisabled, AllViewerExceptHostHeader and zero supported error-cache TTLs; preserve Authorization/query strings and discard cookies/viewer identity headers |
| DEMO `/api` and `/api/*` | JSON 503/no-store from the static routing function; no API origin or forwarding |

Keep API errors separate from SPA navigation. Do not add distribution-wide 403/404-to-index mappings. A function URI rewrite does not select a different cache behavior. Reject ambiguous paths according to the existing [static router](../../infra/portfolio/frontend-static/routes.js.tftpl) and [API router](../../infra/portfolio/frontend-static/api-routes.js).

## Archify and content security

The [asset adapter](../../frontend/scripts/architecture-assets.mjs) checks approved original hashes, sanitizes repository/source metadata and generates content-addressed JSON presentation assets. Do not upload the raw source/HTML directory as a substitute for a verified package.

The viewer verifies bytes and uses an opaque iframe sandbox with scripts/downloads but no `allow-same-origin`. Preserve the embedded network-denying CSP, the parent script hashes, MIME/nosniff and direct-data asset policy. Generated JSON is data, not a public executable HTML alias. See [Archify maintenance](../development/architecture-explorer.md).

## Reproducible release and rollback

Build from the reviewed source using pinned Node/npm and the lockfile. The existing packager binds mode, inventory, lengths, digests and media/cache metadata; verify against an independently recorded package digest. `sourceBaseCommit` alone does not prove a clean tree. Use a verified clean commit or archive and retain source provenance.

Upload only approved immutable objects, conditionally. Verify bytes, metadata and VersionIds before selecting a release. A normal DEMO selection changes the routing function's release digest; it does not require a new distribution, API or bucket. Verify LIVE code and public behavior, not merely Terraform success. Retain old objects for old tabs and a reviewed rollback.

Returning AWS → DEMO requires removal of API forwarding as well as selecting DEMO bytes. An existing AWS tab must show unavailability; reload selects DEMO without retaining its memory session. If deleting API helpers, first detach them, wait for distribution deployment and confirm no consumers before deletion. Never use a retired runtime to repair static hosting.

## Evidence and limits

[Results](../results.md) separates the public AWS trial, return to DEMO and final static publication from local simulated release tests. The latter cannot prove CloudFront propagation, real authentication or database rollback. Hosting has an explicit owner and expiry; release selection does not renew it. Keep costs, retained versions and rollback plans within that scope.
