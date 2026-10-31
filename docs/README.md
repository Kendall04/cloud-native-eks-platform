# Documentation

Start with the [project overview](../README.md), try [Logistics Demo](https://d3ujivegzs1gn7.cloudfront.net/demo), or explore the [five architecture diagrams](https://d3ujivegzs1gn7.cloudfront.net/architecture).

The runtime was retired on 29 October 2026. The static DEMO was published on 30 October. These dated results do not assert current AWS availability; see [evidence and limitations](results.md).

## Understand the system

| Question | Guide |
| --- | --- |
| How do requests and events reach the services? | [Platform architecture](architecture/current-platform.md) |
| Who owns each stack and dependency? | [Infrastructure](architecture/infrastructure.md) |
| What protects users, workloads and data? | [Security](security.md) and [architecture decisions](adr/README.md) |
| How do DEMO, AWS mode and static hosting differ? | [Frontend hosting](architecture/frontend-hosting-decision.md) |
| What was actually demonstrated? | [Results](results.md) and [28–29 October closure](operations/eks-cycle-2026-10-29.md) |

## Run and contribute locally

- [Frontend quick start](../frontend/README.md), [local PostgreSQL/API setup](development/frontend-local.md) and [release/browser checks](development/frontend-release.md).
- [Toolchain and validation](development.md).
- [Archify source, generation and integrity](development/architecture-explorer.md).

## Operate an authorized lab

| Task | Procedure |
| --- | --- |
| Rebuild after cost-down | [Reconstruction prerequisites](operations/post-cycle-rebuild.md), then [deployment](operations/deployment.md) |
| Reach private EKS or PostgreSQL | [Private access](operations/private-access.md) |
| Manage secrets and migrations | [Secrets and database](operations/secrets-database.md) |
| Deliver or recover an application release | [Private CD](operations/private-cd.md) |
| Diagnose asynchronous processing | [Events](operations/events.md) |
| Recover NAT | [NAT recovery](operations/nat-recovery.md) |
| Retire the runtime safely | [Lab cleanup](operations/lab-cleanup.md) |
| Publish a static DEMO release | [Static promotion](operations/frontend-demo-promotion.md) |

Runbooks describe procedures, not authorization. Historical evidence is dated; an old plan, identity or resource inventory cannot authorize a new operation. Private state, credentials and original receipts stay outside Git.
