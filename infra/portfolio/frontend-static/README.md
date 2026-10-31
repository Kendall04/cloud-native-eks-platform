# Separate retained DEMO host

The initial source increment was local preparation only. Hosting B was subsequently published under separate owner approval; see the [live record and original expiry](../../../docs/evidence/frontend-static-live-20261022.json). This source does not grant standing authority for later actions or the EKS runtime cycle. See the [review packet](../../../docs/architecture/frontend-hosting-decision.md) and [persistent-effect inventory](../../../docs/operations/frontend-static-preparation.json).

This standalone Terraform root serves the existing explicitly synthetic Product Demo and Architecture Explorer. It has one private, versioned S3 REST origin, OAC and CloudFront distribution. Its default DEMO state has no API origin. Explicit AWS mode may reference the existing regional HTTP API using two ordered behaviors and two additional controls, validated against the final existing environment contract. It creates no API, domain registration, ACM certificate, KMS key, IAM role or connection to the EKS eighteen-state graph. The viewer function rejects API calls and origin writes. Default creation leaves the distribution disabled; publication and enabling it are separate reviewed effects.

Use exactly Terraform 1.13.4 and AWS provider 5.100.0. The required `execution_principal_arn` must match the actual caller in account 341936017254. This identity check does not confer authority. Never substitute the preflight administrator as an implicit execution design.

Any future execution must keep private state, plans and credentials outside Git and outside EKS's backend. Copy this small root to the approved private execution directory or configure a separate private data/state location; retain its source hashes and state lineage. Do not execute it inside the EKS teardown owner. Do not apply a mocked plan or the unbound review JSON.

Prepare the local inventory from an already verified DEMO package with `frontend/scripts/hosting_plan.py`. It validates the existing package contract and writes a new review file exclusively. Promotion/rollback options only describe a target and an expected current release; they do not upload, select, authorize or guarantee a remote rollback. Capture fresh resource IDs, state and ETag before any cloud action. Retention dates and allowance do not renew on selection.

`terraform test` uses a mocked AWS provider, including a synthetic caller identity. No credentials or AWS API calls are needed. The route checks and cached-artifact Chrome fixture are described in the review packet. They do not certify actual CloudFront HTTPS, S3 denial or edge propagation.

The [22 October closure](../../../docs/operations/eks-local-cycle-closure-2026-10-22.md) records the API behavior, candidate existing executor, same-package offline test and guarded synthetic DB proposal. Owner is Kendall; source tags are not a substitute for his concrete normal action approvals.
