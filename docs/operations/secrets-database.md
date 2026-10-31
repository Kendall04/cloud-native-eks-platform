# Secrets, database and migrations

[Deployment](deployment.md) · [Private access](private-access.md) · [Security](../security.md)

Terraform creates Secrets Manager containers and IAM permissions, not application secret payloads. Phase 2 initializes missing values, ESO reconciles them into Kubernetes, and database bootstrap uses the RDS-managed master secret only for role/schema setup. Runtime pods use neither master credentials nor migration identities.

| Concern | Owner / behavior |
| --- | --- |
| Auth JWT and gateway proxy trust | Shared Secrets Manager sources consumed by authorizer/ESO |
| Internal service authentication | Separate platform secret for Tracking→Shipment |
| Runtime and migration DB credentials | Separate identity per service/schema |
| Initial administrator | Seeded by Auth's migration path; not runtime escalation |
| SecretStore, service accounts, CA, RBAC | Platform bootstrap release |
| ExternalSecrets | Secret-sync release; ESO is the Kubernetes Secret writer |
| Schema migrations | Application Helm Jobs using migration users |

[database.py](../../scripts/bootstrap/database.py) creates/configures roles transactionally, schema ownership, existing/default object privileges and isolation. Runtime users receive application data permissions; migration users own their service schema. TLS uses VerifyFull and the pinned public RDS CA. A CA bundle is public trust material, not a private key.

Phase 2 requests fresh ESO reconciliation, captures metadata versions, bootstraps DB roles and rechecks those versions before writing `platform-db-bootstrap`. Phase 3/CD compares that marker with current secret versions. A mismatch means rerun authorized platform reconciliation; do not edit the marker to bypass the gate. The marker is an ordering check, not protection from an administrator of the apps namespace.

## Rotation

Rotate only in an authorized operator session. Inventory consumers and preserve recovery access first. Update the intended Secrets Manager version without logging values, then reconcile ESO and database credentials in a controlled maintenance window. Re-run phase 2 to reconcile DB role passwords and the version marker. Review active application connections before rollout. Secrets injected through environment variables require pod replacement; ESO updating a Secret alone does not refresh a process environment.

The Lambda authorizer caches secrets in memory for its configured TTL. JWT signing-secret rotation can invalidate issued tokens; coordinate Auth/authorizer propagation. Shared proxy/internal secrets also require coordinated consumer rollout. No dual-key seamless rotation protocol is claimed. Do not put secret versions into ad-hoc artifact overrides; publish a reviewed application artifact when delivery metadata changes.

## Migration and recovery

Migration hooks are separate from runtime probes/selectors. Auth's migration path also seeds the initial administrator. Migration errors fail delivery; use bounded diagnostics and inspect the authorized Job without dumping Secrets or connection strings. Repeat only after identifying whether its transaction committed.

Helm restores application resources, not database contents or schema. Keep migrations compatible with the previous application release. Database backups/snapshot restore are separate recovery operations; Single-AZ RDS and seven-day configured backup retention do not establish a measured RTO/RPO. The final lab teardown purged its database/data; historical successful integration does not imply that data can now be recovered.
