# Local synthetic integration and remaining admission boundary

[Implementation](README.md) | [Qualification receipt](../../../docs/evidence/eks-synthetic-qualification-20261027.json)

The existing environment-contract producer now consumes the data output locally.
The same package/publication entry points and host contract carry its explicit
environment and UUID namespace. This source integration is not execution admission.

| Existing source | Implemented local behavior |
| --- | --- |
| `scripts/bootstrap/environment.py`: `generate` and `build_contract` | Explicit synthetic packets are selected before settings, STS or historical output reads. Closed fields, account/region, UUID, namespace, classification and protected identities are validated. No fallback on missing data. |
| The same file: identity/contract validation | Synthetic ESO, workload and addon roles must be supplied explicitly and pass the namespaced/protected-reference checks. No retained helper fallback or identity creation. Legacy helpers retain their original behavior. |
| The same file: `overlay` and generated `platform.values.yaml` | New host, event bus, queue URLs, environment telemetry, ten secret mappings and supplied workload roles feed the existing Helm data flow. ALB group uses the trial namespace. |
| `scripts/bootstrap/bootstrap.py`: phase1 | Synthetic phase1 only compiles the local contract, without any owner apply, output or AWS call. Other synthetic runtime phases reject by default. Dev phase behavior is preserved. |
| Packaging, export/publication, orchestration and host contract | Synthetic environment schema3 becomes artifact schema2, requires capability1.5.0 and carries the exact `dataScope` into trusted target validation and receipts. New environment prefixes are explicit. Dev environment schema2/artifact1/capability1.4.0 remain closed and unchanged. |

The producer maps the new output's `database`, `secretArns`, `eventBus`,
`queueArns`/`queueUrls` and `consumerDlqArns`/`consumerDlqUrls` into the existing
typed contract. Its logical delivery environment is explicitly `trial-<UUID hex>`;
the namespace is `cnp-trial-<UUID hex>`. It never relabels trial data as dev.
The required local packet also contains explicit settings, account, infrastructure
outputs, roles/encryption bindings and integration metadata. The root alone does
not provide those. A supplied binding/hash is not evidence of a real resource,
native generation, effective permission or approved access.

`environment.py --synthetic-input <packet.json> --environment <trial-environment>`
uses the existing generator. `package()` requires explicit expected environment
and data scope. Export uses `--environment` and `--synthetic-scope`; publication
and orchestration use explicit `DEPLOYMENT_ENVIRONMENT` and `SYNTHETIC_DATA_SCOPE`.
Missing or dev-mismatched scope fails. Image-record provenance remains in its
existing immutable build namespace; data-contract/artifact/receipt namespaces
use the explicit trial environment. No workflow variables were changed.

The host validates the complete closed snapshot, protected identities, trusted
scope and binding hash before accepting normalized values. A changed DB host,
queue, bus, telemetry environment or scope is rejected even after checksums are
recomputed. Existing chart hashes, data-only restrictions and replay guards stay
in place; receipts cannot be adopted under changed bindings.

Create a newly validated, immutable environment-contract version before normal
release packaging; preserve source SHA, VersionId/hash, digest and compatibility
checks throughout. Never rewrite an existing published bundle, checksum, receipt
or checkpoint to make the new data fit. The retirement runner remains untouched.

Existing IAM prefixes and the SSM document's dev-only input pattern are unchanged.
The new capability has not been installed on a host. These are concrete live
admission blockers, not permission to broaden access or update a pin automatically.

## Exact protected bindings that still need a decision

The current no-reuse guard rejects all of these. Their presence here is a review
reference and does not add an allowlist or change a policy.

| Field | Exact preserved reference | Narrow question for review |
| --- | --- | --- |
| `bindings.vpc_id` | `vpc-05a8ec8d7de5a8271` | May this be referenced only as the VPC of newly created trial data resources, with no VPC deletion/adoption or implicit route mutation? |
| `bindings.private_subnet_ids` | `subnet-046105462ce63d6e2`, `subnet-008e047cc76640549`, `subnet-084c508e189051a45` | May only these existing private subnet identities feed the new DB subnet group after ownership/AZ review? Original routes and associations remain protected. |
| `bindings.event_kms_key_arn` | `arn:aws:kms:us-east-1:341936017254:key/88e09005-a830-4f4f-90e3-493fe721272f` | May this exact enabled event key encrypt only the new trial queues after consumer/policy review, with no inferred key-policy, alias, grant or deletion change? |

`workload_security_group_ids` stays unbound until fresh trial workload/management
groups are observed and reviewed. The existing RDS group is not an acceptable
substitute. Original RDS, all11 secrets, existing queues and historical state
keys/lineages remain denied regardless of any network/key decision.

The renderer names a separate intended backend bucket; it does not create it.
That backend's provisioning, rights, retention and cost need an explicit reviewed
disposition. Switching to a new prefix in the retained backend would also be a
protected-reference decision, never an automatic fallback.

No substitute VPC/key/backend is created to avoid a refusal. Native ownership and
generation proofs, NAT compatibility,
private restore proofs, retention, access approval and the prior destructive-action
refusal remain separate unresolved gates. Local qualification is not admission.
