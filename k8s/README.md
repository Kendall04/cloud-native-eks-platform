# Kubernetes

| Chart | Owner and purpose |
| --- | --- |
| `cluster-addons` | Operator: LBC, Cluster Autoscaler, Metrics Server, KEDA and ESO |
| `platform-bootstrap` | Operator: identities, RBAC, CA, SecretStore, KEDA auth and NetworkPolicies |
| `platform-secret-sync` | Operator: ExternalSecrets |
| `platform-services` | Application CD: services, migration hooks, scaling, PDB and Ingress |

Use the [deployment sequence](../docs/operations/deployment.md); chart values require generated AWS identities and real image digests. `environments/prod/` is a validation overlay, not deployed production. [Database and migration ownership](../docs/operations/secrets-database.md) explains why runtime pods do not initialize schemas or use master credentials.
