# Logistics Platform Demo — Cloud Native Platform EKS

A small React/TypeScript workspace for the existing Auth, Shipment and Tracking APIs. Dark presentation, responsive navigation, shipment forms and tracking timelines. AWS is not required or contacted by this local setup.

## Start on Windows

Use the pinned Node.js **24.18.0** (`.node-version`) and bundled npm **11.16.0** (`packageManager`), then run from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173/demo** for Logistics Platform Demo or **http://127.0.0.1:5173/architecture** for the public Architecture Explorer. The default is **DEMO**, visibly labelled everywhere. `npm run dev:demo` selects DEMO explicitly. Demo login needs no credentials, makes no API requests and keeps synthetic changes only until reload. It never substitutes for a failed real request.

`.env.example` documents the public `VITE_APP_MODE` (`demo`, `local` or `aws`) and same-origin `VITE_API_BASE` (default `/api`). No secrets belong in `VITE_*`. `dev:demo` and `dev:local` explicitly select their mode. Normal `dev` defaults to DEMO unless configured otherwise.

## Modes and routes

| Mode      | Command                                                         | Data and access                                                            |
| --------- | --------------------------------------------------------------- | -------------------------------------------------------------------------- |
| DEMO      | `npm run dev:demo`                                              | Four synthetic shipments, local changes reset on reload, no backend calls  |
| Local API | `npm run backend`, then `npm run dev:local` in another terminal | Real local .NET/PostgreSQL; AWS messaging disabled                         |
| AWS build | `npm run build:aws`                                             | Same-origin `/api`; requires separately authorized API hosting and runtime |

The normal `npm run build` produces DEMO unless explicitly configured otherwise. Never put credentials in public Vite configuration. AWS failures remain visible errors, never synthetic fallback. Tokens remain in memory and disappear on reload; the UI does not use refresh tokens.

**Logistics Demo** uses `/demo`, `/demo/shipments`, `/demo/shipments/new`, `/demo/shipments/:id` and `/demo/tracking`. **Architecture Explorer** is public at `/architecture`. It has five diagrams, guided reading, a complete map and a text alternative. `/architecture/security` presents Security & Trust Boundaries; `/architecture/lifecycle` retains an explicit historical transition. Explorer receives no application tokens.

## Development

```sh
npm run typecheck
npm run lint
npm test
npm run build
npm run check:architecture
```

Use [local APIs and PostgreSQL](../docs/development/frontend-local.md) for backend setup, API capabilities, persistent local data and authentication boundaries. New shipments do not automatically create tracking events; the UI does not expose administrative event creation.

Use [frontend release and validation](../docs/development/frontend-release.md) for Playwright, real local API checks, CI behavior, packaging and simulated release transitions. Test fixtures are not AWS evidence. Use [Archify maintenance](../docs/development/architecture-explorer.md) before editing diagrams or pins; CI verifies approved artifacts rather than regenerating them.

## Reproducible local static package

The existing `scripts/package_static.py` accepts a built directory, explicit mode and source commit. It produces an immutable archive with a manifest and checksums; verify it against a trusted SHA256. Source provenance must reflect the actual tree, not just an arbitrary `--source-base` value.

See [package commands and verification](../docs/development/frontend-release.md#reproducible-local-static-package) and [publication procedure](../docs/operations/frontend-demo-promotion.md). Keep private reports, credentials and receipts out of public assets. The static S3/CloudFront host is independent of EKS; publishing requires separate approval and never extends its retention automatically.
