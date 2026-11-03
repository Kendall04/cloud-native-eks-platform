# Local APIs and PostgreSQL

[Frontend quick start](../../frontend/README.md) · [Validation](../development.md)

Commands below start from the repository root in each terminal. This is a local Docker/PostgreSQL environment; it does not provision AWS.

## Local API with PostgreSQL

Prerequisites: Docker Engine/Desktop with Linux containers, .NET SDK **10.0.403**, network access for the initial locked restore, and free localhost ports **5173, 8080–8082 and 55435**. No Kubernetes, AWS identity or cloud emulator is needed.

In one terminal:

```powershell
cd frontend
npm run backend
```

This starts a separately labelled PostgreSQL **15.18** container, restores/builds the three APIs, runs their existing migrations and starts them on loopback. `CNP_DOTNET` can select an installed SDK executable without changing `global.json`. The launcher generates local passwords/trust keys under ignored `.validation-results/local-ui/backend.json`; preserve this file with the database. It never prints these secrets. Local-only PostgreSQL uses a single development database owner; this is not the production role separation or TLS topology.

In a second terminal:

```powershell
cd frontend
npm run dev:local
```

Open **http://127.0.0.1:5173** and choose **Create an account**. Auth requires an email and a password with uppercase, lowercase, number and symbol, at least eight characters. Registration creates an ordinary user. No fixture password is checked into the repository.

Ctrl+C in the launcher stops only its API processes. PostgreSQL and the named volume `cnp-local-ui-postgres-data` remain intact. Stop the database explicitly with `docker stop cnp-local-ui-postgres` if desired; do not delete its volume or regenerate its matching secrets file. Restarting the launcher reuses the database and idempotent migrations. Unknown containers/volumes/networks with matching names are rejected by ownership labels. A failed startup writes private diagnostics to ignored `.validation-results/local-ui/launcher-error.log`.

## API capability matrix

The authority is the service controllers and DTOs linked below. Responses are checked at runtime with Zod; malformed data is rejected.

| Capability           | Real contract                                                  | UI scope                                                                                                         |
| -------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Register / login     | `POST /auth/register`, `POST /auth/login`                      | Account creation and login; no preloaded credentials                                                             |
| Session identity     | `GET /auth/me`                                                 | Profile, roles and account status; USER/ADMIN authorization remains server-side                                  |
| Refresh              | `POST /auth/refresh` exists                                    | Not used; expiry requires signing in again                                                                       |
| Logout               | No revoke/logout endpoint                                      | Clears memory locally; does not revoke previously issued JWTs                                                    |
| List                 | `GET /shipments?PageNumber=1&PageSize=20&Status=CREATED`       | Real pagination and optional status filter                                                                       |
| Detail               | `GET /shipments/by-id/{guid}`                                  | Route, weight, reference, priority, current shipment status and timestamps                                       |
| Create               | `POST /shipments`                                              | Customer ID is the authenticated user's ID, origin/destination, weight, optional reference/priority              |
| Tracking             | `GET /tracking/by-tracking-number/{number}`                    | Recorded history, status, location, notes, sequence, source and timestamp                                        |
| Other lookups        | `GET /shipments/by-tracking/{number}`; tracking by shipment ID | Tracking search reads the shipment status using the first route; the second remains available in the local proxy |
| Admin changes/events | Separate admin controllers                                     | Not exposed through the UI proxy; no edit/delete/cancel action                                                   |
| Dashboard            | Shipment paged response                                        | Total count is server-provided; status counts are explicitly current-page counts, not global aggregates          |

Sources: [Auth controller](../../microservices/auth-service/src/AuthService.Api/Controllers/AuthController.cs), [Shipment controller](../../microservices/shipment-service/src/ShipmentService.Api/Controllers/ShipmentsController.cs), [Tracking controller](../../microservices/tracking-service/src/TrackingService.Api/Controllers/TrackingController.cs), [Shipment DTOs](../../microservices/shipment-service/src/ShipmentService.Application/Contracts/Shipments), [Tracking DTOs](../../microservices/tracking-service/src/TrackingService.Application/Contracts/Tracking).

Shipment supports eight symbolic statuses: CREATED, PICKED_UP, IN_WAREHOUSE, IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, DELAYED and CANCELLED. These are displayed, not synthesized into transitions. A shipment's current status and its tracking event history are separate read models. Creating a shipment does not automatically create a tracking event. A new local shipment therefore has an empty timeline. Existing recorded events are supported; the UI does not invent them or expose admin writes.

## Local security boundary

Vite's development proxy binds to loopback and allows only documented routes, methods, expected Host and same-origin/absent Origin. For every protected request it calls Auth `/auth/me`, which validates the JWT signature, lifetime and active account. It forwards this verified identity and the original bearer to Shipment/Tracking using a server-only generated proxy secret. The backend independently checks the current Auth profile and matches its user ID to the attested identity; it uses current roles rather than the snapshot header. This is a local implementation; the associated NetworkPolicy/TTL source changes are now implemented in [ADR-005](../adr/005-current-profile-authorization.md), with scoped EKS/gateway enforcement demonstrated during the October 28–29 lab cycle. Browser-supplied platform identity/internal headers are discarded. Auth failure is fail-closed. Development JWT passthrough is explicitly disabled in the launcher. This milestone changes backend authentication checks; it does not change production CORS, authorizer configuration or RBAC.

Access tokens exist only in memory; refresh tokens are discarded. Reloading requires login. This avoids persistent browser token storage but is not protection against script injection while a session is active. No JWTs are logged. Errors are deliberately generic and do not render backend exception details. HTTP 400/401/403/404/409/500, connection failure, timeout and invalid payloads have distinct client handling. A 401 clears the session. Shipment/Tracking deliberately return 404 for other users' resources to avoid existence disclosure.

SQS consumption and EventBridge outbox dispatch are **disabled** only in the local launcher. Internal Tracking→Shipment lookup and PostgreSQL persistence still operate. No AWS messaging, scaling, EKS, rollout or cloud integration is claimed by these tests. Production bootstrap, Private CD 1.4.0, Terraform, Helm, protected pins and the nine IaC/Kubernetes exceptions are untouched.
