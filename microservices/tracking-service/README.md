# tracking-service

Tracking HTTP API and transactional outbox dispatcher; tracking schema. POST /admin/tracking-events requires Admin. Only TrackingStatusUpdated v2.0 is published.

HTTP `status` and `sourceType` accept defined symbolic names (case-insensitive),
not JSON numbers or numeric strings. The application validates both enums before
lookup/sequence allocation; the domain independently rejects undefined values.
Invalid input creates neither a TrackingEvent nor an OutboxMessage and consumes
no durable sequence. Shipment retains its independent payload validation.

Targets .NET 10 LTS; use root global.json SDK. Production health: /health/live (process) and /health/ready (PostgreSQL). Swagger is Development-only. Production credentials come from ESO-managed Secrets; root validation runs this solution. Images are built once and promoted by digest through the private CD artifact, not manually pushed as latest.

See [architecture/routes](../../docs/architecture/current-platform.md), [current operations](../../docs/README.md), and [validation](../../docs/development.md).

## Explore and test

`src/` separates API endpoints, application contracts, domain rules and infrastructure/persistence. `tests/` contains the service tests. From the repository root, using the SDK pinned in `global.json`:

```sh
dotnet restore microservices/tracking-service/TrackingService.sln --locked-mode
dotnet test microservices/tracking-service/TrackingService.sln --no-restore
```

Database-dependent checks need the explicit PostgreSQL prerequisites in [development](../../docs/development.md); a skipped test is not database validation. For a working local application with generated development credentials, use the [three-service PostgreSQL launcher](../../docs/development/frontend-local.md). Do not copy production secrets into local configuration.
