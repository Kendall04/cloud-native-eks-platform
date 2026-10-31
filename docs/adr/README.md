# Architecture decisions

These decisions describe the implemented design. See [results](../results.md) for the completed lifecycle and remaining limits.

| ADR | Decision |
| --- | --- |
| [ADR-001](001-event-encryption.md) | One environment CMK for active event queues |
| [ADR-002](002-bootstrap.md) | Explicit phased LBC→Terraform discovery |
| [ADR-003](003-event-reliability.md) | Atomic outbox, stable identity and per-aggregate sequence |
| [ADR-004](004-private-cd.md) | Immutable artifact and fixed SSM private deployer |
| [ADR-005](005-current-profile-authorization.md) | Current Auth profile behind gateway attestation; local implementation and approved network/cache source contracts |

Subsequent accepted decisions, without duplicating runbooks:

- [Secrets/DB identity](../operations/secrets-database.md): platform-owned ESO, separate schema/runtime/migration credentials, TLS and bootstrap ownership.
- [Autoscaling/observability](../security.md): Auth/Tracking CPU HPA, Shipment SQS KEDA min2, dedicated KEDA IRSA, soft spread/PDB, standard CNI policies, CloudWatch OTel + EMF, no full tracing stack.
- [Evidence boundary](../results.md): observed runtime outcomes, current offline state and untested scenarios.
