# Recoverable EKS cycle admission: 27 October 2026

[Documentation](../README.md) | [Curated receipt](../evidence/eks-cycle-admission-20261027.json) | [NAT recovery](nat-recovery.md)

**NO_GO before creation.** The current owner request authorizes pursuing the cycle
within USD30 AWS, USD8 total Actions, 12 hours from the first new billable resource,
and closure starting before hour6. It does not approve unspecified access changes
or bypass retirement guards. This audit does not reopen CI or GitGuardian.

## Source and observed inventory

The remote main was read using the existing Git credential helper. An independent
local clone binds commit `09a1dc08140b1a14f7b2a662609b7ed96fff538b` and tree
`ec989a7220ffd7ed99700642a9b1f1b8a8ceec5b`, matching the recoverable contract.
The original checkout, its WIP, remote configuration and history were preserved.
The GitHub connector returned404; it was not treated as repository absence or a
reason to change credentials. The existing Git transport succeeded.

AWS observations at **06:23:20–06:23:44 UTC** verified the expected operator,
account and region. Regional EKS listing was empty; EC2 inventory in the protected
VPC was empty. Project-tagged EBS and named platform ASG queries were empty.
These scopes are not a complete account inventory or proof of global absence.

The protected RDS generation matches its version-bound Terraform state: stopped,
encrypted, private,20GiB, seven-day automated backup retention and deletion
protection enabled. Its existing automated snapshot is available. A separate read
confirmed the RDS encryption key is AWS-managed and enabled; key availability is
not the blocker. Snapshot availability does not prove a successful restore.
The original RDS must not receive trial application traffic or migrations.

The tag query returned11 secrets and3 queues, and the publisher/orchestrator
roles, their shared boundary and the shared GitHub OIDC provider were readable.
These identities exist and must not be assumed absent or recreated blindly.
Their effective authorization was not tested. Three protected private default
routes remain blackholes. CloudFront configuration was captured privately;
original hosting object bytes/versions were not requalified in this audit.

Six backend objects were read by exact S3 VersionId, without init, refresh, import,
state writes or locks. Their serials/counts are in the curated receipt. Counts
refer to recorded managed instances, not independently live AWS resources.

## Acceptance matrix for this cycle

| Requirement | Actual result | Remaining gate |
| --- | --- | --- |
| Source and contract identity | PASS: exact main/tree and four contract-file hashes | New execution changes require their own reviewed source identity |
| Preserve existing resources/data | Metadata and six state bindings captured; no AWS mutation | Full native/state ownership reconciliation before any saved plan |
| Isolated synthetic data | NOT IMPLEMENTED by current dev bindings | Separate trial DB, secrets, queues, API and artifact identities; protected generations excluded |
| Two recoverable copies | NOT PROVEN; existing automated snapshot only | Current-data private restore proof, then final trial-data private restore proof before dependent retirement |
| Infrastructure plans | NO ADMISSIBLE SAVED PLAN | Reject protected changes/replacements and mocked dependency outputs; bind fresh real plans |
| OIDC / Build → Release → Deploy | NOT RUN; existing roles observed | Approved access delta, environment/host bindings, workflow/ref/SHA, VersionId/hash and deployed digests |
| Authentication / authorization / backend / events | NOT RUN | Real isolated runtime; no substitution of historical or simulated checks |
| NAT / observability | NOT RUN | Reviewed predecessor ownership, activation, quiescence and compatible owner retirement |
| Real web A → B → A and old authenticated tab | NOT RUN | Two real source releases, served hashes, real API withdrawal and explicit reload into DEMO |
| Retirement | NOT RUN / NOT APPLICABLE to new resources | No new resource was created; current absence is a baseline, not a new teardown pass |
| Delivery | Local private review branch and evidence prepared | Final delivery remains incomplete until real cycle and retirement pass |

## Concrete source and state incompatibilities

1. `infra/live/dev/rds/terragrunt.hcl` selects the protected database name, and
   `dev/rds/terraform.tfstate` still owns that exact native generation. The shared
   runtime/authorizer-secret stacks, queues and event bindings similarly select
   retained identities. Applying the standard dev bootstrap is not an isolated
   synthetic trial. A new environment label alone is not proof that all consumers,
   IAM resources, state keys and immutable artifact contracts were isolated.
2. NAT state serial38 records21 legacy instances, including3 static EC2 and3 EIP
   associations, while main declares ASG/controller ownership. The fresh VPC query
   contains no EC2 instances. This is unreconciled state, not a reviewed migration.
   `nat_recovery_enabled=false` and `approved_predecessor_enis={}` remain the live
   defaults. The three blackhole next hops require exact ownership proof.
3. [The NAT procedure](nat-recovery.md#migration-from-partially-retired-state--plan-only)
   explicitly says the previous teardown catalog/retention plan is not qualified
   for the new resources. Recovery adds protected journal/failure resources and
   new quiescence requirements. Neither disabling guards nor silently selecting
   the historical NAT source is an admissible solution.
4. The older rejection record identifies a destructive RDS-without-backup and
   EKS/network retirement request, rejected before process creation. The new owner
   instruction supplies execution intent; it does not turn that rejected request
   into an admitted plan. No rejected command, alternate runner or principal was
   attempted here. No fresh automatic-review rejection occurred in this audit.

## Grouped access review required before application

This is a review inventory, **not an executable approval packet**. Actual trial
identities and resolved policy bytes are not yet bound. Do not approve or apply
an unbound wildcard substitute. The following changes must be presented together
once the isolated execution source and retirement path are qualified:

| Group | Bounded intended access | Required evidence before apply |
| --- | --- | --- |
| Trial workloads / ESO | Dedicated trial roles; exact fresh issuer, audience and service accounts; only trial secret ARNs and event resources | Rendered trust/identity/boundary bytes and resource list; retained ESO and11 secret identities unchanged |
| Private CD | Preserve repository subjects/audience and actor separation; exact trial images/artifact namespaces, SSM document and observed management host | Current publisher/orchestrator grants versus proposed grants; no wildcard host, new static key or broader GitHub trust |
| NAT recovery | Main's controller policy scopes SourceDestCheck, EIP association, private routes and journal slot writes | Three exact route tables/predecessors, fresh allocations and ASG slots; controller role/policy and retention/quiescence review; no foreign route or CONTROL writes |
| Private recovery probes | Access only to the two private restored databases and their required secret/key references | Dedicated SGs/principals, encryption readback, no public route or use of original DB by trial applications |

New generated IDs must be observed at their proper stages, not invented or
pre-attested. Any change to an existing boundary, trust, key policy, protected
resource or original route requires an explicit reviewed delta before application.
The current blocker requires a supported compatibility/admission review of this
concrete isolated lifecycle. An additional generic owner confirmation cannot
replace the missing plan, restore proofs or retirement compatibility.

## Cost, retention and evidence

The accepted contract model is **USD24.864707 plus USD5.135293 contingency**, under
USD30; it is a proposal model, not a fresh price quote or invoice. Stop admitting
tests at USD24 consumed/committed and protect the remaining closure reserve.
Actions have **USD6.966 remaining** after the supplied USD1.034 model; no workflow
was enabled, dispatched or rerun here. Before creation, reprice the isolated plan,
including two snapshots, up to13 secrets, private restore probes, retained NAT
evidence and other residuals. No new runtime was created and T0 has not started.
Read requests were made; their marginal cost and the actual bill were not queried.

The earlier retained-resource reference remains about **USD11.50/month**, excluding
unmeasured S3/hosting/backups/requests and other account costs. The existing RDS
automatic restart is **1 November03:42:19.447 UTC**; this audit did not change it.
Keeping RDS stopped does not remove storage charges. Existing schedules and data
are protected; this cycle does not authorize cleaning them up.

New copies, secrets and private evidence require at least30days and explicit later
review, with no automatic purge. Raw inventory, version-bound states, configuration
and hashes are outside both Git checkouts. The curated receipt exposes only bounded
results and hashes. No token, secret value, kubeconfig or state is committed.

The README status and this matrix distinguish current baseline from historical
results. Architecture source diagrams remain unchanged because no topology was
deployed; their intended-design status is explicit in README. Historical acceptance
and original evidence remain intact. Page/bitácora receive the same blocked status.

## Subsequent local isolation implementation

The [synthetic data renderer](../../infra/trials/synthetic-data/README.md) now
implements a separate, UUID-bound data configuration instead of using dev data
bindings. Its194-selector policy rejects protected identities, and its outputs
connect only newly declared RDS/secrets/queues/event resources. No cloud operation
or existing module, live stack, IAM policy, CD/retirement runner or baseline pin
was changed. The earlier NOT IMPLEMENTED row describes the inspected main/dev
source; this local partial root is not integrated into that execution path.

The strict no-reuse guard also leaves preserved network/key exceptions and the
new intended backend unresolved for later review. Those inputs remain unbound;
no alternate network/key creation is inferred. Full bootstrap integration,
restore proofs, access approval and admitted retirement remain blockers.

### Subsequent local producer/CD integration

The existing producer, phase1 entry point, packager, export/publication metadata,
orchestration target and host contract now carry the synthetic namespace explicitly.
Synthetic phase1 performs local generation only and cannot apply protected owners.
The versioned synthetic contract is separate from the unchanged dev schemas.
The [integration result](../evidence/eks-synthetic-delivery-local-20261027.json)
uses real local Helm rendering with cloud adapters replaced by fixtures. It is not
real AWS publication or runtime evidence. Protected VPC/KMS exceptions, effective
IAM/SSM admission, host installation, restore proofs and retirement remain blocked.
