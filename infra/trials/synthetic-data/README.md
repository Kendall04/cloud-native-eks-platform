# Local synthetic data configuration

[Admission record](../../../docs/operations/eks-cycle-admission-2026-10-27.md)

`scripts/bootstrap/synthetic_trial.py` renders a separate Terraform JSON root for
new synthetic RDS, ten secret containers, three queues and a dedicated event bus.
It reuses the existing child modules and provider lock without changing them.
It does not run Terraform, AWS, bootstrap, CD or retirement.

Supply a newly selected UUIDv4 namespace, not a future AWS resource ID:

```powershell
python scripts/bootstrap/synthetic_trial.py --trial-id <uuid-v4>
python scripts/bootstrap/synthetic_trial.py --trial-id <uuid-v4> --check .generated/synthetic-trials/<uuid-v4>/main.tf.json
```

The output has a new intended state bucket name and run-specific key; neither the
backend nor any resource is created. RDS, secret names, queues and bus names are
derived from the complete UUID. Queue policies refer only to the newly declared
queues. Data outputs refer only to these child modules. There is no `dev` include,
remote-state read, original secret import, existing database restore, ESO/IAM role,
secret payload or fallback. RDS protection/backups/final snapshot remain enabled;
all new secret containers use a30-day recovery window. No purge is scheduled.

The network/encryption input object has **no defaults**. Optional `--bindings`
accepts an explicit JSON object with exactly `vpc_id`, `private_subnet_ids`,
`workload_security_group_ids` and `event_kms_key_arn`. Values must be real IDs
observed and separately reviewed later. The renderer does not discover or certify
them. Production examples deliberately contain no fabricated IDs.

The protection policy projects194 exact selectors from the previously captured
contract/state evidence, plus historical namespace prefixes. It includes the
protected RDS identity/endpoint,11 secret ARNs, queues, state keys/lineages and
network identities. Original evidence remains outside Git. The validator rejects
these selectors anywhere in configuration or supplied bindings, including encoded
or qualified references. An artifact check also rejects changed policies/locks,
additional Terraform/import/override/state files and altered bindings. Rendering
refuses overwrite and symlink traversal; it never merges an existing state.

This deliberately strict local configuration cannot yet be bound to the preserved
network or existing event key: those are protected too. The approved contract's
possible shared-reference exceptions require a separate, concrete review. The
renderer does not create a new key/network or broaden any grant to work around
that conflict. A new intended backend also needs its own reviewed disposition;
there is no backend bootstrap here.

The existing producer now consumes this data root through an explicit local
synthetic input packet. Synthetic snapshots use environment schema3, artifact
schema2 and an exact UUID namespace/binding hash. Legacy dev keeps schema2,
artifact schema1 and its original1.4.0 contract; no old schema was relaxed.
The synthetic host capability is1.5.0 source only, not an installed upgrade.
ESO/workload access, private restore probes, snapshots, retention enforcement
and live runtime wiring remain outside this local increment.
A30-day secret recovery window is not proof that the full retention/recovery
contract was met. Neither this root nor its output is an admitted execution plan
or a replacement retirement path. The earlier refusal and remaining NAT/retirement
compatibility blockers persist.

Focused offline regressions:

```text
python -B -m unittest discover -s scripts/validation -p test_synthetic_trial.py -v
```

The [initial local result](../../../docs/evidence/eks-synthetic-isolation-local-20261027.json)
records21 passing tests on Python3.12.14. The subsequent
[exact-version qualification](../../../docs/evidence/eks-synthetic-qualification-20261027.json)
uses existing WSL Python3.13.17 and portable official Terraform1.13.4:21 Python
tests, provider/schema validation and5 mocked plan cases pass. Backend initialization
is disabled; AWS5.100.0 comes from the existing cache with the unchanged lock.
The initial pending qualification is historical; neither result is cloud acceptance.

[The implemented local integration](INTEGRATION.md) identifies the existing
bootstrap/CD consumers and exact protected network/key decisions. It does not
implement those exceptions, modify the retirement runner or authorize backend
provisioning. The [integration receipt](../../../docs/evidence/eks-synthetic-delivery-local-20261027.json)
records producer-to-artifact-to-consumer tests using real local Helm rendering
and simulated cloud adapters, not real publication or deployment.
