# Publish a reviewed static DEMO release

Use the existing portfolio CloudFront/S3 host under explicit publication authorization. This runbook does not authorize uploads, Terraform or retention renewal. Runtime EKS is unnecessary. Original hosting retention ends **21 November 2026 at 01:04 UTC**. The [30 October publication](../results.md#static-publication-30-october-2026) is a dated example, not permission for another selection.

## Integration and source identity

1. Use the reviewed commit integrated into main with successful required CI. Verify current ancestry and the actual tree diff; do not replay resolved historical branch conflicts as a publication prerequisite.
2. Fetch and fast-forward a clean main checkout in the original directory. Preserve all local WIP first; do not use reset/clean. Record the exact final 40-character HEAD and verify it equals origin/main. Require empty `git status --porcelain` and successful CI on the code reaching main.
3. The approved local package `ae973868749ae99c4957e5d6443c4a76e2d692dec33eba34e203a97671eb4f4b` remains review evidence only. Its `sourceBaseCommit` is an ancestry reference to a modified working tree, not the final main identity. Build a new package after integration; do not relabel old bytes.

## Build and inspect locally

Use the locked Node/npm versions from `frontend/.node-version` and `package.json`, with the existing locked dependencies. The following commands perform no AWS operations:

```powershell
$ErrorActionPreference = 'Stop'
$Source = (git rev-parse HEAD).Trim()
if ((git status --porcelain) -or $Source -ne (git rev-parse origin/main).Trim()) { throw 'Clean integrated main required' }
# Choose an existing ignored evidence directory and a fresh filename.
$Package = '.validation-results/frontend-package/demo-main-' + $Source + '.tar.gz'
Push-Location frontend
try {
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw 'TypeScript failed' }
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw 'Lint failed' }
    npm test
    if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed' }
    npm run build -- --mode demo
    if ($LASTEXITCODE -ne 0) { throw 'DEMO build failed' }
    npm run check:architecture
    if ($LASTEXITCODE -ne 0) { throw 'Architecture integrity failed' }
} finally { Pop-Location }
python frontend/scripts/package_static.py build --dist frontend/dist --mode demo --source-base $Source --output $Package
if ($LASTEXITCODE -ne 0) { throw 'Package failed' }
$Digest = (Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash.ToLowerInvariant()
python frontend/scripts/package_static.py verify --artifact $Package --mode demo --sha256 $Digest
if ($LASTEXITCODE -ne 0) { throw 'Package verification failed' }
```

Retain the new SHA256, manifest, source commit and exact file inventory. Require all five new diagrams, Security at `/architecture/security`, the explicit historical Lifecycle transition, Logistics Platform Demo branding, matching Archify 3.1.0 pins, offline iframe CSP and opaque sandbox. Check DEMO sessions, no API traffic, keyboard/touch, deep links and representative Chrome viewports. The packager uses immutable output creation and scans its closed inventory; no credentials or raw operational evidence enter it. Repeat the build if claiming byte reproducibility.

## Prepare the selection review

After future authorization for AWS reads, recover the **existing independently owned hosting state**, its backups, lineage/serial, exact IDs, selected release, VersionIds and CloudFront ETag. Never recreate/import hosting automatically or target EKS's backend. The recovered state has a documented replacement lineage; the lost original lineage must not be invented. Any identity or consumer mismatch blocks publication.

Use the existing `frontend/scripts/hosting_plan.py` locally with `--operation promote`, the new package/digest and `--current-release` from that verified readback. The output is a review inventory, not a native Terraform plan or permission to mutate. Its generic retention proposal is historical preparation metadata: it does **not** replace the existing owner's expiry or authorize renewal. Do not supply an API domain or runtime contract.

For the later native hosting plan require **site_mode=demo**, **api_enabled=false**, **api_domain_name=null**, the new **release_sha256**, and the existing enabled distribution, private S3 origin and OAC. Use Terraform 1.13.4 and locked provider versions with the trusted private state and plan paths. Review the complete native plan: only static routing/release selection should change; no resource creation, deletion, replacement, bucket/backend/IAM/runtime changes or API origin/behaviors. The empty-OAI normalization is already integrated; any new provider/state drift still requires separate review and must not be hidden in a release switch.

## Publication acceptance

- Publish only the exact planned immutable asset/release keys with the existing conditional `If-None-Match=*` operations. On collisions, compare bytes and metadata; never overwrite silently. Record actual VersionIds and checksums. Keep all prior versions/releases.
- Apply only the reviewed saved hosting selection plan under separate authorization. Verify the function in LIVE and its selected digest; a function-only update need not change the distribution ETag. Require the distribution to be `Deployed`, then read back ETag, selected release, one S3 origin, zero API behaviors/origin and enabled status. No invalidation, purge or retention reset is implied.
- Through public HTTPS, verify manifest/source/digest, DEMO's four synthetic shipments, local creation reset, tracking, five diagrams/deep links, assets/MIME/CSP and zero DEMO backend requests. `/api`, `/api/shipments` and `/api/auth/me` must return JSON **503/no-store**, never SPA HTML.
- Check old static assets remain accessible. A retained AWS tab must show honest unavailability without synthetic fallback; reload selects DEMO without JWT/cookies/storage session. Do not claim this as rollback between different authenticated AWS versions.
- On an unsuccessful selection, inspect the real result before recovery; select a retained verified DEMO through another explicitly reviewed plan. Never enable API forwarding or rebuild runtime to fix static hosting.

See [hosting ownership](../../infra/portfolio/frontend-static/README.md), [original retention record](../evidence/frontend-static-live-20261022.json), [frontend packaging](../../frontend/README.md#reproducible-local-static-package) and [cycle closure](eks-cycle-2026-10-29.md).
