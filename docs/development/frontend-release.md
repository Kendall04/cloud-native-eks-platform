# Frontend release and validation

[Frontend quick start](../../frontend/README.md) · [Hosting design](../architecture/frontend-hosting-decision.md) · [Static promotion](../operations/frontend-demo-promotion.md)

Run commands from the frontend directory unless a section explicitly says repository root. These checks do not publish or authorize AWS operations.

## Reproducible local static package

### Local simulated release lifecycle

The two explicit `LOCAL_SIMULATED` regressions build frozen AWS A, AWS B and DEMO
fixtures, then serve only loopback with synthetic intercepted Auth/API responses.
B changes the authenticated overview title through an isolated `App.tsx` source
overlay; tracked application source is unchanged. Each version has a distinct
bundle hash and documented source hash. B is a test variant, not a committed or
deployed product release. A continuously loaded AWS document must display an
honest unavailable error until explicit reload; it does not silently become DEMO.
The same tab then loads DEMO without persistent auth or API calls. A separate
test promotes and rolls back A/B/A and checks the actual served JS identities.

With pinned Node/npm, the existing Python packaging dependencies and installed
Chrome, from this frontend directory:

```powershell
npm run build:release-fixtures
$env:CI = 'true'
$env:UI_TEST_MODE = 'release-lifecycle'
$env:UI_RELEASE_ATTEMPT = 'attempt1'
npm run test:browser -- --workers=1 --retries=0
```

Preparation refuses to overwrite existing fixtures. Rerun those same frozen
fixtures with a fresh attempt label to preserve prior results; use a fresh checkout
when qualifying changed application source. Outputs stay under ignored
`.validation-results/frontend-release-lifecycle/`: separate packages/manifests,
source-overlay bytes, per-attempt receipts, JUnit and synthetic screenshots.
Contexts and the owned server close normally; no personal browser session or
numeric-PID termination is used. These opt-in checks do not activate remote CI.
They establish local browser/selection contracts, not real CloudFront propagation,
real authentication, arbitrary upgrade compatibility or database rollback.

The existing asset generator now emits each diagram, curated evidence JSON and license under `architecture-assets/<full-sha256>/<name>`. The generated viewer URLs use those paths; diagram HTML integrity and the iframe sandbox are unchanged. Vite retains its content-versioned JS/CSS names. A final `frontend-build.json` receipt contains only public mode/API-prefix configuration, Node version and the exact output inventory with SHA-256/length. It does not dump environment variables.

From the repository root, with existing Python CD dependencies and the frontend dependencies already available:

```bash
(cd frontend && npm run build:aws)
python3 frontend/scripts/package_static.py build --dist frontend/dist --mode aws \
  --source-base <reviewed-base-40-hex> --output .validation-results/frontend-package/aws.tgz
python3 frontend/scripts/package_static.py verify \
  --artifact .validation-results/frontend-package/aws.tgz --mode aws --sha256 <trusted-artifact-sha256>
python3 -m unittest discover -s scripts/validation -p test_frontend_package.py -v
```

Use the ordinary DEMO build and `--mode demo` for a separate synthetic artifact. The packager reuses Private CD's sorted USTAR/gzip writer, canonical JSON and bounded archive reader without changing them. It writes `manifest.json`, `checksums.sha256` and `site/` into an immutable local `.tgz`; an existing output is never overwritten. Verification requires an external expected digest and explicit expected mode. It rejects stale/mixed inventories, absent/tampered files, unexpected paths, symlinks, credential patterns and entrypoint URLs outside the package. No files are extracted by the CLI.

The manifest binds mode, `/api`, every file's digest/length and media/cache metadata. Media/cache fields describe the publication contract; they do not configure a server or prove HTTP headers. `sourceBaseCommit` is an explicitly supplied provenance base, not a clean-source attestation. Checksums establish integrity against the trusted expected artifact SHA; they are not signatures or authority against an attacker who can replace that expected SHA. Reproducibility was checked with two fresh builds per mode on the same existing Linux toolchain, not across arbitrary OS/tool versions.

The packager itself does not upload, select releases or perform rollback. Retaining an earlier local bundle alone does not keep old browser tabs working after a hosting switch. See the [static promotion procedure](../operations/frontend-demo-promotion.md).

## Checks and production build

From the repository root:

```powershell
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
npm run format:check
npm run check:architecture
npm audit
# Running backend + dev:local required; creates uniquely named local test records:
npm run test:api
# Uses installed Chrome, no browser download:
npm run test:browser
# V2 architecture, fullscreen, export, responsive and automated accessibility tests:
$env:UI_TEST_MODE = "v2"
# Requires a DEMO server on 5173 (or set UI_TEST_URL to a production preview):
npm run test:browser
Remove-Item Env:\UI_TEST_MODE
# Against a separate DEMO dev server on 5174:
$env:UI_TEST_MODE = "demo"
npm run test:browser
Remove-Item Env:\UI_TEST_MODE
```

Start the separate DEMO server with `node node_modules/vite/bin/vite.js --mode demo --port 5174`. Component tests use isolated mocks; the API script uses real services/PostgreSQL. Browser tests use actual Chrome and check both modes, navigation, form submissions, persistence after reload, visible failures and a 390 px viewport. Test outputs/screenshots remain ignored. Synthetic demo timestamps/IDs are not experimental evidence.

`npm run build` generates `dist/`, including the five adapted JSON exports, curated evidence and Archify license; `npm run preview` serves the default DEMO production build on **http://127.0.0.1:4173**. The local API proxy is development-only and is not included in production assets. The AWS-mode build still needs reviewed hosting/same-origin routing to the authorized API Gateway endpoint, SPA fallback and browser-origin policy. Do not deploy the Vite dev server or expose the internal ALB/EKS.

Static hosting must serve actual files first, then fall back to `/index.html` for application paths such as `/demo/shipments/...` and `/architecture/platform`. Missing `/architecture-assets/*` must return 404, not the SPA shell. Serve JS, JSON, CSS, SVG and text with correct MIME, keep the data exports inert, use HTTPS for Web Crypto/fullscreen and retain the viewer sandbox/CSP. The current build assumes deployment at the origin root. Development and `vite preview` support deep-link reloads locally; local preview does not prove deployed hosting headers.

## Troubleshooting

- Port in use: stop the previous launcher/dev server or identify the owning process. Strict port handling prevents silent changes.
- Backend unavailable: check all three `/health/ready` endpoints on 8080–8082 and the SSH tunnel, when used. Check ignored private launcher logs locally.
- SDK mismatch: install/use 10.0.402; do not relax the SDK pin.
- npm TLS interception: use your organization's trusted CA through `NODE_EXTRA_CA_CERTS`. Never disable strict TLS.
- Registration rejected: check password complexity or use a different email. Existing accounts return conflict.
- Empty tracking: expected for newly created shipments; local startup does not run AWS workers. DEMO history is visibly synthetic.
- Dependencies: use `npm ci` with the checked-in lockfile. No GitHub Actions execution is needed for local development.

## GitHub Actions validation

The `frontend` job pins the toolchain in `.node-version` and `packageManager`, uses a lockfile-keyed npm cache, and runs all quality, build, dependency-audit and Archify checks. `npm run check:lock` includes an offline negative `npm ci` test in a disposable directory. Chrome supplied by the runner runs Logistics Demo and all Explorer suites against a real production preview. In CI, Playwright starts/stops that preview automatically; `UI_TEST_MODE=portfolio` selects the synthetic portfolio browser suite.

The existing PostgreSQL reliability job reuses PostgreSQL 15.18 and the .NET/NuGet setup for `npm run test:api:ci`. This runner-only command requires `CI=true`, a disposable `platform_ui_ci` database on loopback PostgreSQL (5432 by default), the pinned .NET SDK, and free ports 5173/8080–8082. It runs the 22 HTTP assertions plus private-file denial and both real API browser tests. `CNP_UI_POSTGRES_PORT` can select a different local test port. It never starts/removes the developer PostgreSQL volume. Private generated credentials/logs stay in ignored `.validation-results/local-ui-ci`; no AWS messaging is enabled.

Seven-day validation artifacts contain reports and synthetic browser failure diagnostics. LOCAL API traces are disabled, and private configuration/process logs are not uploaded. The production build is not published to hosting. Adding a diagram still requires reviewing/pinning its original artifact, extending the catalog/export registry and exercising the viewer tests; CI verifies those inputs instead of regenerating Archify originals.
