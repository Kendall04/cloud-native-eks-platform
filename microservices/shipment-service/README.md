# shipment-service

Shipment HTTP API and SQS consumer in one Deployment; shipment schema. Durable inbox/EventId and SequenceNumber handling preserve R5 semantics. No EventBridge publisher.

Targets .NET 10 LTS; use root global.json SDK. Production health: /health/live (process) and /health/ready (PostgreSQL). Swagger is Development-only. Production credentials come from ESO-managed Secrets; root validation runs this solution. Images are built once and promoted by digest through the private CD artifact, not manually pushed as latest.

See [architecture/routes](../../docs/architecture/current-platform.md), [current operations](../../docs/README.md), and [validation](../../docs/development.md).

## Explore and test

`src/` separates API endpoints, application contracts, domain rules and infrastructure/persistence. `tests/` contains the service tests. From the repository root, using the SDK pinned in `global.json`:

```sh
dotnet restore microservices/shipment-service/ShipmentService.sln --locked-mode
dotnet test microservices/shipment-service/ShipmentService.sln --no-restore
```

Database-dependent checks need the explicit PostgreSQL prerequisites in [development](../../docs/development.md); a skipped test is not database validation. For a working local application with generated development credentials, use the [three-service PostgreSQL launcher](../../docs/development/frontend-local.md). Do not copy production secrets into local configuration.
