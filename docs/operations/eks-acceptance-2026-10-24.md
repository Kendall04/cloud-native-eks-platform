# EKS acceptance and local handoff: 24 October 2026

[Results](../results.md) | [27-task evidence matrix](../evidence/eks-acceptance-20261024.json) | [Development](../development.md)

The separately authorized 23-24 October cycle is **closed**. Application source
`5b66456db40bbaa52c4884da231b44d90e6dc6e1` ran on .NET10; retirement source was
`98c0cbe34d8b3a951f8e79a2544012996d2cfd31`. Later prose/presentation changes do
not change image provenance or qualify a new deployment. No push, remote workflow,
publication, new budget or AWS action is part of this local handoff.

The private closure was sealed at **2026-10-24 07:33:53.884233 UTC**, SHA256
`0c1e6ad73e4f6f070b8e0579bc8b16a59124dbb692baba58c71510e11fad12ef`.
The curated JSON projects selected receipt statuses and hashes into 27 stable
task rows; raw users, tokens, endpoints, account/resource identities, state and
payloads remain outside Git. Hashes allow an authorized holder to compare the
originals; they are not signatures or independent public verification.

## Acceptance matrix

| Tasks | Evidence-backed result | Limit |
| --- | --- | --- |
| T01-T02: C0 identity/source/consent/budget | Correct operator/source; new USD25/24h cycle closed | Not authority for another cycle; cost is a model, not invoice |
| T03-T05: C1 network/compute/database | Private EKS, three baseline nodes, PostgreSQL15.18 VerifyFull and migration/runtime gates | One environment; no general HA/RTO claim |
| T06: OCI and scans | Corrected official runtime pins; three digest-bound images delivered | No relabeling images to this documentary HEAD; dated scans |
| T07-T10: C2 authorization/network/preservation | Authorizer TTL0; 29 direct +42 gateway checks;18 CNI flows/bindings; original ESO/ten secret metadata maps preserved | No secret payload export or generic security certification |
| T11-T13: C3 events |53 checks: actual route, duplicate without duplicate effect, distinct late sequence rejected,61-message backlog and recovery after verified pause | Does not prove arbitrary missing-predecessor liveness or exactly-once transport |
| T14-T16: C4 delivery/rollback/scaling | Private CD, controlled failed rollout with compatible corrected-image rollback; worker1-2-1, maximum4nodes, KEDA2-4 and CPU HPA observations | No DB rollback; initial CPU cooldown observation timed out, subsequent automatic return recorded separately |
| T17-T19: web/hosting |13 successful real API/browser checks; distinct immutable DEMO A to AWS-config B to original A; fresh DEMO has no API calls, API503/no-store | Browser run stopped waiting for DEMO; later fresh browser proves return, not continuous old-tab behavior. Not two different authenticated application-source releases |
| T20-T23: C5 | Actual freeze/export,39/39 stages,178 Terraform objects retired,3 external Private CD IAM objects absent;16 empty+2 retained readable states; own locks absent | New key PendingDeletion30days, not physically gone; foreign denied attributes NOT_VERIFIED and never deletion targets |
| T24-T25: hosted Dependabot/CI | Historical evidence retained; current local HEAD not remotely exercised | Authentic security-update PR and fresh full hosted Validate need an explicit repository action |
| T26: npm reproducibility | Laptop locked installation recorded; offline inconsistent-lock rejection and same-toolchain repeat builds are separate local evidence | Not arbitrary-machine or fresh-registry reproducibility |
| T27: knowledge/presentation | This repository reconciliation and local Explorer summary | Parent owns Page upkeep; local changes are not a published hosting release |

The web503 negative was injected in the browser and is not a real AWS outage.
The stopped C3 first attempt, CPU timeout, browser transition timeout and failed
first final-preservation verifier remain identified in the curated evidence.
Later success does not turn those attempts into passes. Test counts above overlap
scopes and must not be added to claim a unique total.

## Security, privacy and retentions

The final image assessment reports **0 HIGH/CRITICAL,2 MEDIUM and1 LOW per image**,
without a reported fixed version for those residuals. The earlier
`ca-certificates` advisory was resolved through verified official base pins and
new image identities before final delivery. This is neither zero vulnerabilities
nor a guarantee of future patch posture. The source/configuration policy retains
**9 scoped exceptions /10 HIGH-CRITICAL occurrences**, expiry **12 January2027**;
the separate build SDK's4 HIGH occurrences are not runtime image findings. No
exception, expiry or suppression was added during closure.

Exact original ESO/trust/inline policies, three original boundaries, ten original
secret identity/encryption/version-stage maps, twelve original hosting objects,
backend/state/history and shared resources were preserved. The new key is
scheduled for **23 November2026 05:16:07.129 UTC**, with all four historical key
schedules unchanged. PendingDeletion is not physical absence; original hosting,
secrets and backend may still incur charges. Hosting retention was not extended.

The final discovery was scoped to EKS ownership. Foreign SQS attributes and sealed
ECS resource attributes remained **DENIED/NOT_VERIFIED**, preserved without a
denied-read retry. Known own targets retained full required coverage. Do not claim
a complete account inventory or use this limitation to authorize any deletion.
The current-tree scan and generated-asset checks are bounded privacy checks;
history, hosted logs and future publication visibility need separate review.

## What the elapsed time actually measures

T0 was23 October22:11:22 UTC; final closure was24 October07:33:53.884233 UTC:
**9h22m31.884s for the whole cycle**, including deployment, remediation, tests,
web restoration, preparation and retirement. It is not nine hours of AWS deletion.

| Recorded boundary, UTC | Observation |
| --- | --- |
|23:27:07-23:32:46 | Phase2 database/TLS/role bootstrap |
|00:02:05-00:04:03 | C2 direct/gateway checks |
|00:43:18-00:52:51 | Successful C3 attempt |
|00:53:30-01:06:39 | Controlled failed rollout/compatible Helm rollback |
|01:07:26-01:11:20 | Worker capacity1-2-1 |
|01:12:32-01:20:48;01:23:18 follow-up | CPU load/cooldown timeout; later automatic return verified |
|01:31:38-01:51:50 |13 web checks; stopped awaiting DEMO |
|02:03:07-02:03:09 | DEMO selection and fresh-browser verification |
|02:36:06 | Retirement journal created |
|02:41:17;02:42:40-02:42:41 | Actual freeze; run-bound export |
|02:43:59-02:47:08 | First owner API-integration stage, including plan/apply/native verification |
|03:57:37-04:13:21 | RDS stage; native DB absence observed04:02:20 |
|04:52:13-05:02:15 | EKS stage, including node/control-plane retirement |
|05:22:34 | Last costly runtime/EIP native absence |
|06:32:08-07:22:48 |33-version S3 purge including stops and verification |
|07:28:16;07:30:12;07:33:53 |39-stage verification; external IAM absence; sealed closure |

These intervals include validation, local corrections, observations and waits;
some overlap. Exact API latency, reviewer wait and user wait were **not separately
measured**, so none receives invented minute totals. DEMO verification to journal
creation was about33minutes of preparation; it is not evidence of AWS latency.

The S3 stage took50m40.908s including stops. Median spacing of successive delete
intents was35.862s, largest gap17m07.591s. The implementation read18states and a
regional inventory before each new version write. Foreign-owner policy/lifecycle
changes, a throttled IAM read and rereading already acknowledged absent versions
caused additional local recovery. These measurements are not S3 request latency.

## Concrete lessons and bounded next work

Local handoff validation used Node24.18.0/npm11.16.0 and existing dependencies:
two fresh output directories per mode produced identical bytes for all11 files
in DEMO and all11 in AWS mode. The four outputs total18,887,862bytes; no duplicated
dependency/provider cache or download was needed. The ignored reproducibility
receipt binds the inventories and byte counts. This proves same-toolchain build
repeatability; it does not prove arbitrary OS/toolchain or fresh-registry restore.
The earlier laptop `npm ci` installation log and this run's offline inconsistent-lock
rejection remain distinct evidence. Toolchain instructions now match the frontend
pin rather than confusing it with the Lambda runtime.

TypeScript, ESLint, formatting,28 architecture tests and all five built Archify
integrity/CSP/inline-syntax/privacy checks passed. CI/security-policy tests had22
passes and3 explicit Windows Bash skips; frontend CI contracts had5 passes.
Documentation links/anchors, R7 integration and current-tree secret checks passed.
The additional static-package suite had11 passes and1 Windows fixture error:
`test_symlinks_are_not_read` could not create its disposable symbolic link
(`WinError1314`, required privilege absent). Its assertions were not reached;
the suite is not a pass. No privileged retry, OS setting change or test relaxation
was attempted. This packaging platform gate remains explicit.
The initial handoff did not rerun browser visuals, Linux Bash behavior, remote CI,
DB suites or image builds. The Linux follow-up below subsequently closes its four
platform cases. Existing144 lifecycle
regressions are reused as the recorded retirement qualification, not rerun or added
to these counts. Mermaid sources and original Archify artifacts were unchanged.
The [local validation receipt](../evidence/eks-local-handoff-20261024.json) records
the build inventory hashes, exact test scope and the initial Windows platform gate.

### Linux and privacy follow-up

The four previously unexecuted cases subsequently **passed in the existing
Ubuntu24.04 WSL environment with Python3.13.17**, zero skips/errors: all three Bash
policy behaviors and the symbolic-link package rejection. Fixtures used Linux
`/tmp`; no Windows privileges, tests, dependencies or OS settings changed. The
original Windows result stays preserved. Across the original Windows run and these
four distinct missing cases,70 selected test identities now have passing execution;
this is not a claim that all70 passed on Windows or that the whole project suite ran.

The [follow-up receipt](../evidence/eks-local-privacy-followup-20261024.json) also
records a bounded privacy review at commit `1a1537ba1bc9b7b060394a19139b76a7c0404ac3`:
227 locally reachable commits,1,957 unique blobs, three ZIPs/members and227 commit
messages. One legacy cp1252 IAM HCL blob was checked separately; no known credential
pattern or non-placeholder sensitive appsettings finding was identified. The added
diff from the retirement source also had no known token pattern. This does not prove
arbitrary secret absence, current GitHub state, hosted logs/artifacts or unreachable
objects. Git metadata, local operational IDs/endpoints and private-repository
references remain privacy context; no values were printed or history rewritten.
The55 commits beyond the imported migration ref are a local comparison, not a
statement that GitHub is55 commits behind.

Two web limits remain precisely defined:

1. Keep one authenticated AWS-mode browser tab open while hosting returns to DEMO
   and the API becomes unavailable; verify the old tab's requests/errors without
   reloading it. The actual cycle observed a fresh DEMO tab instead. Existing
   `frontend/browser/aws.spec.ts` already tests memory-only auth and synthetic
   no-fallback failures, but not that continuous hosting transition.
2. Promote and roll back between **two different authenticated application-source
   releases**. The actual hosting A/B/A evidence used DEMO versus AWS configuration
   packages; compatible Helm/backend rollback is separate and already observed.

Both client contracts can be tested on loopback using distinct static packages
and intercepted synthetic Auth/API responses, with no backend or AWS. Such a fixture
would establish browser/selector behavior, not real CloudFront propagation or real
backend authentication across two source releases. No additional browser test or
hosting change was executed in this follow-up. Decide whether those stricter live
scenarios are acceptance requirements before proposing any extra paid environment.

The owner subsequently required fresh hosted CI/authentic Dependabot qualification
in the current private repository and both stricter real web observations. The
[GitHub admission plan](../development.md) separates local correction,
remote branch/check enforcement and future specifically bounded cloud work.
Any new repository is deferred until the end; no history is deleted. Existing TLS/CSP and
retention exceptions remain documented; changing them would be a separate scope
decision, not an inferred prerequisite to keep the retired backend running.

### Local simulated web lifecycle result

The [two browser regressions](../../frontend/browser/release-lifecycle.spec.ts)
subsequently **passed2/2** in installed Chrome155.0.8059.86, labelled
**LOCAL_SIMULATED**. The [curated receipt](../evidence/eks-frontend-release-lifecycle-local-20261024.json)
binds the immutable fixture versions, actual source hashes and package digests.
AWS A and B differ in `App.tsx` source and served application JS; B is a documented
isolated source-overlay fixture, not a committed/deployed release. Their API
contract remains identical. The build leaves tracked application source intact.

The continuously open old AWS document first received a synthetic503 while still
labelled AWS, without a DEMO fallback. Explicit reload in that same tab loaded the
DEMO artifact, replaced the document, retained no cookies/local/session storage,
performed zero API calls through synthetic creation/reload and restored the original
synthetic list. A subsequent AWS login carried no previous bearer. This is observable
session loss on document replacement, not heap forensics or automatic hot switching.

The second test authenticated with synthetic responses on A, promoted distinct
source bundle B, then rolled back to the exact A package/JS. Each navigation required
a fresh memory-only login; no prior bearer was sent on login. Two owned contexts,
the loopback server and the successful run's Chrome process closed normally.
No API reached even the local static server: all Auth/API responses were intercepted.

The initial attempt timed out on a test selector using ASCII `+` instead of the UI's
fullwidth plus; its failed receipt/capture remain preserved. Corrected attempt2
passed; attempt3 also passed after strengthening restored-DEMO-list and no-server-API
assertions. These repeat runs are two test identities, not four unique tests.
No AWS, backend, new dependency, personal session, publication or history rewrite
was used. Real CDN propagation/authentication across distinct deployed web-source
releases remains unobserved and is now explicitly required; the minimum proposal
is recorded separately, without authorizing new hosting mutations. CI/publication/privacy decisions
remain independent and do not require recreating the retired backend.

Implemented corrections preserve exact KEEP identities instead of requiring their
absence; bind expected post-owner disappearance to positive apply/native/state
proofs; identify our SSM observations without adopting foreign commands; read actual
retired dependency state instead of replanning it; and parameterize the current
cycle's validated deadline/owner rather than using the previous cycle's IDs.
Finite foreign-owner evidence permits expected external lifecycle changes without
granting deletion eligibility. IAM read throttling now has bounded retries;
AccessDenied is not retried. Acknowledged absent storage versions are not rewritten
or independently refreshed on resume; new writes and final convergence remain guarded.
The final focused offline set had144 passes,0skips; earlier overlapping retests are
retained separately, not added to that count.

Before any future paid cycle, replay the relevant transitions locally and qualify
all owner representations together. Prepare retirement/retention consequences,
scope-equivalent consent evidence and one authorized finite lifetime from the
start; avoid arbitrary shorter expiries and overnight response dependencies.
Actual tool denials must still be respected. A local follow-up may measure
adapter read/write costs and evaluate bounded version batching with partial and
uncertain-outcome fixtures. **No batching, engine redesign or new cloud trial was
implemented or authorized by this note.**

The minimum remaining work is fresh hosted CI/authentic Dependabot verification
and server-enforced branch protection in the existing private repository;
privacy/visibility review before eventual publication or migration; and the now
required real CDN proof of two different authenticated web-source releases and a
continuous old-tab transition beyond the scoped local A/B/A demonstration.
TLS/CSP limitations remain explicit security tradeoffs requiring a separate
decision to change. General AZ failure, exhaustive gap recovery, DB rollback,
production certification and physical key deletion are not claimed. None of the
documentation or remote-repository tasks requires recreating the backend.
