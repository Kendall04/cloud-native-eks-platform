# Development and validation

[Documentation](README.md) · [Deployment](operations/deployment.md)

Use .NET SDK 10.0.403 (`global.json` disables roll-forward), Python 3.13 and the pinned tools used in `.github/workflows/validate.yml`: Terraform 1.13.4, Terragrunt 0.93.3, Helm 4.2.2, Node 24.18.0 with npm 11.16.0 for the frontend, actionlint 1.7.12 and ShellCheck 0.11.0. The separate Lambda authorizer runtime is declared by its module; it is not the frontend build-tool version. Install Python dependencies from `scripts/bootstrap/requirements.txt` and `scripts/ci/requirements.txt`. Provider/chart/SDK downloads may need network access; local validation does not require AWS credentials.

## NAT recovery checks

Run `python -B -m unittest discover -s scripts/validation -p "test_nat*.py"` and `python -B scripts/validation/package_nat_recovery.py --check` for fake-SDK recovery/configuration tests and the deterministic Lambda ZIP. Regenerate that ZIP with the same packager after reviewed runtime edits; do not hand-edit ZIPs. See [NAT recovery](operations/nat-recovery.md) for limits and the separately authorized migration. These commands perform no AWS calls.

## Full source validation

```bash
python3 -m pip install -r scripts/bootstrap/requirements.txt -r scripts/ci/requirements.txt
python3 scripts/validation/validate_release_candidate.py --mode local
```

The entrypoint restores/builds/tests services, validates contracts, Helm, Terraform, workflows and current-tree secrets, writing ignored `.validation-results/` artifacts. Missing tools fail. External disposable PostgreSQL prerequisites are explicit; missing integration prerequisites return nonzero by default. `--allow-external-skips` permits a labelled local-only result, not full verification. CI requires actual PostgreSQL 15.18 and rejects skipped integration tests.

`release/candidate.json` remains immutable metadata for the earlier `portfolio-v2-rc1` construction freeze. Its `runtimeCertified: false` describes that historical candidate, not the later lifecycle results. Deployment artifact versions still use `vMAJOR.MINOR.PATCH`. Do not repurpose construction metadata or old tag labels as application versions.

## Focused checks

For documentation changes, run link/anchor checks, Markdown lint, Mermaid parsing/rendering where available, the current-tree scan and whitespace checks. Do not rebuild Docker or deploy AWS to validate prose.

```bash
python3 scripts/validation/validate_docs.py
python3 scripts/validation/secret_scan.py
git diff --check
terraform fmt -check -recursive infra
terragrunt hcl fmt --check --working-dir infra/live
python3 scripts/validation/validate_r7.py
python3 -m unittest discover -s scripts/validation -p test_r7.py
```

Terraform module validation uses `terraform init -backend=false -input=false -lockfile=readonly` then `terraform validate` in a disposable copy, as the full validator does. No live backend or Terraform apply/plan is needed. Helm fixtures under `scripts/validation/fixtures/` are static test inputs, never deployable environment values.

For app changes run relevant service tests and the required PostgreSQL suites; run `python -B scripts/ci/regressions.py all` for the active Python regressions. The archived executor tests are no longer a CI family. Read-only discovery and AWS mutation are separate operational permissions. Never invoke deployment/export/teardown execution as a local validation shortcut.

Generated output, source caches, private evidence and state stay ignored. Preserve provider locks, chart locks and the reviewed public RDS CA. Its byte checksum and executable platform files have specific line-ending rules in `.gitattributes`.

## CI V2

[Public CI evidence](results.md#public-ci-3-november-2026) records automatic PR and push runs in this repository. Links to the original repository below are explicitly historical/private provenance, not the primary public validation record.

`Validate` runs on PRs targeting `develop`/`main`, pushes to those branches, and reusable calls. It has read-only repository permission and no AWS identity. PR validations superseded by a new commit can be cancelled. AWS image publication is now manual-only; Build, Release and Deploy remain disabled in GitHub after teardown. No source change enables those workflows remotely.

The existing .NET, PostgreSQL, authorizer, Terraform and Helm gates remain required workflow jobs. Regression discovery is partitioned into two exhaustive, disjoint families (`platform` and `lifecycle`) instead of one serial step. Run both locally with `python3 scripts/ci/regressions.py all`. A PostgreSQL-dependent skip in ordinary Python discovery remains explicit; the separate required PostgreSQL jobs reject skipped integration tests. TRX and security artifacts are retained for 14 days in Actions.

Dependabot proposes weekly version updates to `develop` for Actions, nested Terraform modules/live directories, NuGet, Docker and pip. Compatible updates are grouped; major updates stay separate. Separate default-branch entries set `open-pull-requests-limit: 0`: they customize security PRs with `chore(deps): ...` without opening duplicate version PRs. GitHub creates security updates against the default branch regardless of `target-branch`; [GitHub documents this distinction](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-security-updates).

A maintainer must inspect a security PR's actual GitHub author (`dependabot[bot]`), linked advisory, changed files and base diff, then retarget it to `develop` and require a fresh complete Validate run. Do not infer identity from a title, branch name, commit email or the workflow actor. Review the diff again after retargeting; shared base differences can change it. The bot receives no main-branch bypass, AWS identity, elevated event or auto-merge permission. Updates enter `main` only through this repository's own `develop` branch. GitHub-generated merge commits are excluded from commit-subject lint; ordinary commits remain checked. Reviews must preserve matching module/live provider locks and the SDK pin; a bot proposal is not approval to change those contracts.

### Reproducible restore and containers

All 16 .NET projects have checked-in NuGet lockfiles. Restore defaults to locked mode in service props and the shared reliability project. CI caches NuGet by lockfiles and pip downloads by requirements. It tests already-built assemblies with `--no-build --no-restore`.

The Docker SDK is 10.0.403 on Ubuntu Noble, matching `global.json`; SDK and ASP.NET Core 10.0.14 runtime images are pinned to verified linux/amd64 manifest digests. Each service context copies its project lockfiles before restore, preserving useful Docker layers. Runtime bases use Noble chiseled-extra, retaining ICU/time-zone data, CA certificates, UID 1654 and port 8080. Update SDK/tag/digest/global.json together after verifying the replacement; do not blindly accept a bot change that breaks the SDK contract. The SDK 10.0.403/runtime 10.0.14 update addresses [CVE-2026-111497](https://github.com/dotnet/runtime/security/advisories/GHSA-p3jp-9v83-76w9). This is an offline build/CI remediation, not a new AWS deployment; historical October runtime evidence retains its observed versions. NuGet libraries are reviewed separately from the shared runtime and remain locked unless affected.

For an intentional dependency update, regenerate locks with the reviewed SDK, then prove a locked restore:

```bash
dotnet restore microservices/auth-service/AuthService.sln -p:RestoreLockedMode=false
dotnet restore microservices/auth-service/AuthService.sln --locked-mode
dotnet build microservices/auth-service/AuthService.sln -c Release --no-restore
dotnet test microservices/auth-service/AuthService.sln -c Release --no-build --no-restore
docker build --platform linux/amd64 -t cnp-ci/auth:local microservices/auth-service
```

Repeat for Shipment/Tracking and `tests/EventReliability.Tests/EventReliability.Tests.csproj` when shared dependencies change. PR/push builds produce three local amd64 images, never push them, and need no AWS. Manual publication skips those duplicate container jobs, builds/publishes through the unchanged CD producer, then pulls and scans the exact ECR digest. Scan failure fails the build run, so Release cannot promote it; the already-published image/record remain for reconciliation. Reused immutable images receive fresh reports without rebuilding. There is no persistent Docker layer cache configured yet; measure its value before adding one.

### .NET 10 compatibility

All 16 projects target `net10.0`: twelve production API/application/domain/infrastructure projects, three service test projects and the shared EventReliability test project. The SDK is 10.0.403; ASP.NET Core/EF Core packages use 10.0.13 and the PostgreSQL provider/driver use 10.0.3. C# remains explicitly at version 12 in service props; this migration does not adopt unrelated language features. The Node.js authorizer is unchanged.

Existing EF migrations, snapshots and database contracts are unchanged. Tests compare all three provider models against their existing snapshots and prove that an incompatible model is rejected before changing migration history. ASP.NET forwarded-header configuration uses `KnownIPNetworks`, preserving the previous configured trust behavior. HTTP/event schemas, roles, JWT validation, outbox/inbox and delivery semantics remain unchanged.

```bash
python3 scripts/validation/verify_locked_restore.py
# Requires Docker, OpenSSL, psycopg and already-built local baseline/candidate images:
python3 scripts/validation/dotnet10_runtime_gate.py \
  --baseline-tag sdk426 --candidate-tag dotnet10
```

The Docker gate requires `cnp-ci/{auth,shipment,tracking}:sdk426` built from the pre-migration .NET 8 tree and the corresponding `:dotnet10` images built from this tree. Tags are configurable; it does not download historical application images or publish images. It uses disposable PostgreSQL 15.18, localhost ports 55434 and 18080–18083, generated TLS/credentials, distinct migration/runtime roles, production configuration and a read-only root with a 64 MiB memory-backed `/tmp`. It verifies unchanged columns/indexes/constraints/migration histories across the upgrade, existing .NET 8 credentials/tokens, readiness, HTTP/JSON/authentication and persisted outbox creation. AWS workers are disabled only in this local fixture; real SQS/EventBridge delivery is outside its scope. Results and fixture TLS material stay ignored in `.validation-results/`.

The [migration evidence](evidence/dotnet10-migration.json) records local checks and the separately identified [34-job PR validation](https://github.com/Kendall04/cloud-native-platform-eks/actions/runs/38709946875). The later [24 October acceptance](operations/eks-acceptance-2026-10-24.md) records the actual .NET 10 runtime and corrected-image compatible rollback in AWS; do not attribute that evidence to the older migration PR or this later documentary HEAD. Fresh hosted Validate of the local handoff remains separate. Runtime is now offline.

### Trivy and SBOM

Trivy 0.71.2 is pinned with an upstream archive checksum. The source job scans NuGet lockfiles and Python manifests, Terraform modules, Dockerfiles and rendered Kubernetes from all four locked charts. Generated bin/obj/provider trees are excluded. Container jobs scan application/runtime dependencies and separately generate CycloneDX 1.7 JSON. Vendored official schemas validate the SBOM offline; [schema provenance](../scripts/ci/schemas/README.md) records their origin.

```bash
bash scripts/ci/install-tools.sh "$PWD/.validation-results/ci-tools"
export PATH="$PWD/.validation-results/ci-tools:$PATH"
python3 scripts/validation/helm_dependencies.py
python3 scripts/ci/security.py source
python3 scripts/ci/security.py image --service auth --image cnp-ci/auth:local \
  --output .validation-results/security/auth
python3 scripts/ci/security.py validate-sbom \
  --report .validation-results/security/auth/sbom.cdx.json
```

Raw vulnerability/configuration reports, findings, policy decisions, SBOM and metadata stay in ignored `.validation-results/security/` and Actions artifacts. Metadata records scanner/database information, scan time, commit, dirty-tree status, workflow run/attempt, local image ID and SBOM hash. Local image IDs are not registry digests. Publication adds the actual ECR digest to the metadata; SBOM inventory and vulnerability results remain separate. No signatures or provenance attestations are generated.

### Initial security policy

New **HIGH/CRITICAL** vulnerabilities or misconfigurations block CI, whether or not a fix exists. LOW/MEDIUM/UNKNOWN findings remain visible as advisory. Tool, download, parse and schema errors fail the job. Trivy's report command uses exit code zero for findings so that the separate policy evaluator can classify them; scanner execution failures are never ignored.

The [reviewed baseline](../scripts/ci/security-baseline.json) retains 9 of the original 83 unique scoped exceptions in the reviewed hardening tree, expiring **12 January 2027 UTC**. Dependency remediation first reduced 83 to 26; the locally and Actions-tested hardening removes 17 more. The explicitly authorized follow-up updates only reviewed template/construction pins and requires executor policy 1.4.0; integration follows the validated PR #56 and controlled develop-to-main promotion. See [the exact boundary](security.md#residual-hardening-proposal-and-integration-boundary). [The evidence](evidence/security-remediation.json) preserves both stages and distinguishes occurrences from unique exceptions/CVEs. Each exception binds scope, target, severity and package/resource evidence. New or expired HIGH/CRITICAL and scanner errors still block. No global exclusions, automatic baseline regeneration or date extension was introduced.

Remaining exceptions concern controller/deployer RBAC, Management HTTPS and two applicability cases. The Auth refresh-token-duration ConfigMap match is a scoped false positive. The EKS encryption check cannot infer [EKS default envelope encryption](https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html); its exception does not claim a customer-managed key or a new AWS test. Existing findings are accepted temporarily, not declared fixed or safe. An empty scan is not a security guarantee. The stricter existing ECR HIGH/CRITICAL promotion gate is unchanged.

Hosted execution is recorded in [CI V2 integration PR #53](https://github.com/Kendall04/cloud-native-platform-eks/pull/53) and [remediation PR #54](https://github.com/Kendall04/cloud-native-platform-eks/pull/54). [Dependabot PR #52](https://github.com/Kendall04/cloud-native-platform-eks/pull/52) exercised full ordinary bot validation after a maintainer fixed generated-merge subject handling. This does not demonstrate automatic generation of a security-update PR. Default-branch configuration changes only become active after reviewed integration into `main`. Inspect individual run logs for cache/timing evidence; local timings do not establish hosted-runner speedups. Interactive delivery diagrams describe the historically demonstrated pipeline; the current trigger table is in [Private CI/CD](operations/private-cd.md#triggers-and-artifact-flow).

## Frontend CI

Validate runs the unconditional `frontend` job for every supported PR, push and reusable call. It pins Node 24.18.0 with bundled npm 11.16.0, restores with `npm ci`, caches npm by `frontend/package-lock.json`, and verifies that an inconsistent lock is rejected. TypeScript, ESLint, formatting, unit/component/proxy tests, production build, dependency audit, compiled-asset credential patterns and Archify integrity all fail the job on errors.

The runner's existing Chrome executes 21 DEMO/Explorer tests against an actual loopback production preview, including five diagrams, fit/zoom/pan, Focus/fullscreen, routes, responsive layout, sandbox isolation and offline CSP. No extra browser download is needed; the installed Chrome version is logged. The existing PostgreSQL reliability job additionally builds the three API entrypoints using its restored NuGet dependencies and disposable PostgreSQL 15.18 service. It runs 22 HTTP assertions, a private-file denial check and two LOCAL API browser tests. AWS workers remain disabled. CI uses a separate ignored `local-ui-ci` configuration, never the developer database/volume or production credentials.

Frontend artifacts retain JUnit, npm audit, build/integrity summary and synthetic browser failure diagnostics for seven days. Real API traces and private launcher logs/configuration are excluded. These reports are validation artifacts, not a hosted release. See [frontend instructions](../frontend/README.md) for local commands and architecture maintenance.

All frontend gates run without path filters or optional success conditions. GitHub branch protection availability still depends on the repository plan; a red Validate run is not a substitute for server-enforced branch protection. Integration must inspect all jobs before merging. No change here enables AWS delivery or configures frontend hosting.

## Current profile authorization milestone

[ADR-005](adr/005-current-profile-authorization.md) records the offline implementation and approved protected NetworkPolicy/TTL source changes, exact-pin regressions and isolated real-Auth/PostgreSQL results. The later [C2/CNI receipts](operations/eks-acceptance-2026-10-24.md) add scoped live AWS enforcement evidence. Focused tests use in-memory Auth HTTP responses and the actual ASP.NET middleware; they do not require PostgreSQL, Docker or AWS. Use the pinned SDK and already-restored dependencies:

```bash
dotnet test microservices/shipment-service/tests/ShipmentService.Tests/ShipmentService.Tests.csproj -c Release --no-restore
dotnet test microservices/tracking-service/tests/TrackingService.Tests/TrackingService.Tests.csproj -c Release --no-restore
```

Run the proxy unit tests after changing bearer forwarding. Do not replace these tests with the previous V2.1/hosting-design reports. A fake Auth result does not certify real JWT/database behavior, gateway forwarding or network enforcement. The two ADR-005 construction deltas have historical exact-hash approval. Their former teardown baseline guard is archived; current platform contracts and source review remain required. Run `python3 scripts/validation/validate_current_profile.py` and the `test_current_profile_contracts` suite for their source boundaries. The manual HTTP gate requires a coordinated local Docker window and cached PostgreSQL; its acceptance and cleanup limits are documented in ADR-005.

## Contribution and delivery boundaries

Validate runs on configured PR/push events. Keep the normal `develop` → `main` promotion direction and inspect the actual tree diff when histories diverge; never change CI policy merely to admit an unrelated branch. Required technical jobs must succeed, with PostgreSQL-dependent skips explicit and rejected where CI requires the database. A policy job skipped on push is not a missing technical check. Manual review discipline is not a claim that GitHub branch protection enforces it.

Build SHA Images, Create Release and Deploy Platform are separate manual AWS workflows and were disabled after cost-down. Local validation does not authorize enabling them, publishing images, deploying or changing repository visibility. Preserve failed-run evidence and immutable artifacts when diagnosing a failure. No public document or historical proposal substitutes for current ownership, identity and mutation approval.

## Documentation changes

Keep the root README focused on the reviewer: purpose, demo, demonstrated capabilities, limits and links. Put reusable commands in the relevant runbook, design rationale in ADRs, and dated observations in [results](results.md). Avoid new per-task progress reports in public operations documentation. Preserve evidence consumed by tests and the Explorer; reference historical records without treating their resource inventories or proposed permissions as current.

Use relative links and repository-relative commands instead of developer-specific paths. When consolidating a page, update incoming references and preserve unique procedures/evidence before removal. Follow [Archify maintenance](development/architecture-explorer.md) for diagrams; documentation edits do not authorize regeneration or pin changes.

## Public repository provenance

This public repository starts from the reviewed portfolio source and consolidated documentation with a fresh Git history. Earlier source hashes, test receipts, Archify evidence revisions and Actions links identify the original development repository; they are historical provenance, not runs or commits in this repository. Original evidence and licensing are preserved. The public repository's Validate results establish its own source checks; no new AWS execution is implied.

Validate requires no AWS credentials. Build SHA Images, Create Release and Deploy Platform remain disabled. The declarative Private CD repository binding names this repository, but existing AWS trusts and installed contracts were not modified or verified by migration. Retired management IDs, environment receipts and historical AWS variables are not reusable configuration. Future delivery requires separate authorization, fresh resources/contracts, reviewed trust bindings and environment variables. Do not enable it merely because CI passes.

### Frontend glob dependency override

The frontend pins the development-only transitive `minimatch` dependency to 11.0.1 for [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249). ESLint and TypeScript-ESLint still request the affected 10.x series, so this is an explicit compatibility override, not an ignored advisory or an automatic major upgrade of the lint stack. Keep locked installation, lint, type checks, application tests and browser checks as compatibility gates. Remove the override only when upstream ranges resolve to a patched version and the same gates pass. `npm audit` retains its full dependency scope and failure behavior.

## Public security artifacts

Validate scans complete source, Docker images and rendered Helm manifests in
`.validation-results/security-private/`. This analysis workspace is never uploaded:
Helm can generate real, disposable TLS private keys even during offline rendering.
Scanner scope, blocking severities and expiring exceptions are unchanged.

`scripts/ci/security_artifacts.py` projects the result into a separate, fresh
`.validation-results/security-public/` directory. Its closed allowlist contains only
`security-evidence.json`: finding identifiers, packages/versions, severities, policy
classification, exception reasons/expiry and selected provenance. Resource excerpts
are represented by hashes. Full Trivy reports, rendered manifests and CycloneDX
properties remain private; the public image evidence retains the SBOM hash and
component count. The full SBOM still undergoes its existing schema validation.

The publication gate validates the actual bytes and schema, rejects unexpected
files/directories, symlinks, archives, private keys, populated Kubernetes Secrets,
embedded manifests and detectable Base64-encoded sensitive content. It fails closed;
errors print only the expected filename and category. No finite scanner detects every
possible secret, so the structural allowlist is the primary boundary.

A failed scan remains a failed job. A separate `always()` step may prepare a bounded
failure diagnostic, but upload requires that staging and its final verification both
succeed. An incomplete scan cannot publish a success report. Regressions use invalid
synthetic key markers, never usable private keys:

```bash
python -B -m unittest discover -s scripts/validation -p test_security_artifacts.py
```

Public Actions artifacts can be downloaded by users with repository read access.
Never apply a manifest downloaded from a validation artifact. Deleting an exposed
artifact does not invalidate previously downloaded copies. Real credential exposure
requires revocation/rotation; disposable offline CI certificates must not be reused.
