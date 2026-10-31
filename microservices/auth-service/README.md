# auth-service

Registration, login, refresh and JWT roles; auth schema. Admin bootstrap runs during the migration path, not arbitrary runtime privilege escalation.

Identity schema policy: retain InitialCreate's 128-character limits for external
login provider/key and Identity token provider/name, plus the filtered unique
normalized user/role name indexes. No current application flow requires wider
keys. AuthDbContext configures these explicitly rather than inheriting framework
defaults; the model regression test compares against committed migrations.
RefreshTokens is a separate unchanged model. This reconciliation requires no DDL
or migration and preserves the existing treatment of NULL normalized names.

Refresh rotation uses a PostgreSQL READ COMMITTED transaction: a conditional UPDATE consumes an
unrevoked, unexpired token, and its affected-row count is authoritative. Competing
updates wait on the same row and recheck the predicate; only one can create a
successor. Consumption and successor insertion commit together; insertion failure
rolls back consumption. A disabled account still commits revocation and returns
the existing forbidden response. Used/unknown/revoked/expired tokens share the
existing invalid-refresh response. No process-local lock or token-family redesign
is involved. Real PostgreSQL contention and rollback tests run in the mandatory
EventReliability suite, whose CI gate rejects skips.

Targets .NET 10 LTS; use root global.json SDK. Production health: /health/live (process) and /health/ready (PostgreSQL). Swagger is Development-only. Production credentials come from ESO-managed Secrets; root validation runs this solution. Images are built once and promoted by digest through the private CD artifact, not manually pushed as latest.

See [architecture/routes](../../docs/architecture/current-platform.md), [current operations](../../docs/README.md), and [validation](../../docs/development.md).

## Explore and test

`src/` separates API endpoints, application contracts, domain rules and infrastructure/persistence. `tests/` contains the service tests. From the repository root, using the SDK pinned in `global.json`:

```sh
dotnet restore microservices/auth-service/AuthService.sln --locked-mode
dotnet test microservices/auth-service/AuthService.sln --no-restore
```

Database-dependent checks need the explicit PostgreSQL prerequisites in [development](../../docs/development.md); a skipped test is not database validation. For a working local application with generated development credentials, use the [three-service PostgreSQL launcher](../../docs/development/frontend-local.md). Do not copy production secrets into local configuration.
