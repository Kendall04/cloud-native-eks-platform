# Historical teardown evidence

The former Python teardown executor has been archived outside the repository. Current operations use [Lab cleanup from Windows](lab-cleanup.md) with Terraform, Terragrunt and AWS CLI. There is no active Python teardown command or CI suite.

The original executor, tests and runbook are recoverable from Git commit `354a5e42c6060300ec29ec1102f8105ae4ef5b12`; the local extraction inventory is in `C:/proyectos/eks-teardown-legacy/manifest.json`. Historical WIP remains on `codex/current-profile-cloud-preparation`. Neither archive nor historical approval authorizes a new AWS operation.

## Lessons from the 20 October retirement

The completed audit corroborates the latest closure: 39/39 stages and 325/326 targets absent/retired, with approved retentions and one scheduled key in that deletion scope. Many final stages verified work already completed in predecessor runs; they were not 39 new destructive operations. RDS was already absent; the observed continuation deleted five auxiliaries. The old 190-resource cycle and current 326-target catalog use different units and dates. See [current results](../results.md#historical-snapshot-21-october-2026) and [source provenance](../evidence/reconciliation-20261021.json).

The audit's final journal spans 10:37:35.194. Its nonoverlapping partition is 00:52:31.947 with an action RUNNING, 08:49:28.988 BLOCKED without another RUNNING action, and 00:55:34.259 elsewhere. Management alone blocked 08:01:50.687 after a successful owner apply because normal terminated-EC2 metadata was rejected. EKS had a similar comparison failure; authorizer checks failed to apply exact approved Lambda exclusions. KMS dependency evidence became stale after legitimate Terraform state writes. Their blocked intervals overlap and must not be summed as exclusive delay. Windows ACLs, omitted Helm identities, private SSM/authentication handoffs, export-contract rejection and admitted deadline/source recoveries also required intervention. Exclusive AWS/provider wait, active repair and human approval durations are not determinable. The 30-day KMS window is separate from operational teardown time.

Preserve exact identity/generation and positive provenance, intent before mutation, UNKNOWN reconciliation before retry, normal Terraform/Helm ownership first and postconditions beyond exit status. Do not copy incident-specific counter/hash recovery chains into every new resource workflow. The executed source contains uncommitted repairs; the documented base does not reproduce them by itself. The closure's 293 regressions are reported historical results with incomplete raw logs; 49 negative cases are corroborated by the audit, not rerun here.

This is a CNP-specific workflow: fixed catalog/DAG/backend/18 state keys and known releases. It is not a generic autonomous AWS engine. Discovery does not establish ownership, approval or a supported deletion action. In particular, the audited orphan adapter does not implement independent EC2 instance termination. Local approval JSON/checksums establish consistency, not authenticated human provenance or protection against an agent controlling all files and credentials. The historical same-user Python credential broker is not a safe capability boundary for Dot. No runtime changes are made here.

For Dot, the minimum **proposal** is external bounded authorization, durable provenance from creation, one typed resource adapter, recoverable intent/journal and absence/retention verification. Prefer one small RDS profile before generalizing; retain EKS as a specialized integration and keep shared backend/data/key authority separate. Generic ownership proof, a hard USD cutoff, TTL scheduling and survival across disconnect/STS expiry/multiple hosts remain unproved. This proposal is not implemented or approved for cloud execution.

## Local comparison repair: 21 October 2026

A separately isolated local baseline repairs three observed EC2 tombstone comparison failures without importing the dirty teardown tree. It requires exact identity/generation, successful owner result and newer explicitly empty state, and preserves unknown/coverage/retained-disk/replacement rejection. No mutation adapter, approval, deadline, credential, transit exemption or retention contract changed. The [baseline preparation record](eks-acceptance-2026-10-24.md) identifies deferred guard changes and the finite future acceptance gates. This is not historical-run recovery or live certification.

## Proposed lifecycle classification

The former executor classification and extension proposals are historical, not an active implementation roadmap. Use the retained/eliminable/absent dispositions and cost-down versus complete-deletion scope in [lab cleanup](lab-cleanup.md). Original proposals remain recoverable at the source commit above.
