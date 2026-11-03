# Cloud Native EKS Platform

[![Validate](https://github.com/Kendall04/cloud-native-eks-platform/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/Kendall04/cloud-native-eks-platform/actions/workflows/validate.yml)

A logistics application built to demonstrate a practical engineering problem: **how to run private services, deliver changes without exposing Kubernetes, and process asynchronous events without duplicating business effects**.

I built three .NET 10 microservices and their AWS platform, infrastructure code, delivery pipeline and interactive architecture documentation. This is a production-like portfolio lab with tested boundaries, not a production service or SLA.

**[Explore Logistics Demo](https://d3ujivegzs1gn7.cloudfront.net/demo) · [Architecture Explorer](https://d3ujivegzs1gn7.cloudfront.net/architecture) · [Results and evidence](docs/results.md)**

The public demo uses **synthetic data only**. The lab is offline after the 29 October 2026 cost-down; delivery workflows are disabled. The static frontend published on 30 October is a separately versioned release, not an automatic deployment of this repository's latest commit.

## What I built

| Area | Design |
| --- | --- |
| Application | Auth, Shipment and Tracking: .NET 10, EF Core and PostgreSQL 15.18 with separate schemas and runtime/migration users |
| Private platform | EKS, Terraform/Terragrunt, API Gateway with Lambda REQUEST JWT authorizer, VPC Link and internal ALB |
| Reliable events | Transactional outbox → EventBridge → standard SQS → durable inbox; stable event IDs, deduplication and sequence handling |
| Private delivery | GitHub Actions/OIDC, immutable ECR digests and versioned S3 bundles, SSM management host and Helm; no direct GitHub-to-Kubernetes access |
| Operations | ALB Pod Readiness Gates, ESO/Secrets Manager, scoped IRSA, KEDA/HPA and per-AZ EC2 NAT recovery |
| Presentation | React/Vite Logistics Demo and five Archify 3.1.0 diagrams, including Security & Trust Boundaries, guided reading and a textual alternative |

## Lifecycle completed: demonstrated in AWS

The **28–29 October cycle** exercised real authentication and persisted shipments/tracking, two event sequences through outbox/inbox, private delivery of v2.0.8, and automatic Helm rollback after a failed smoke. A subsequent deployment used Readiness Gates verified against replacement pod IPs and healthy ALB targets.

One NAT instance replacement restored its EIP and route in **178 seconds** on the controller revision installed for that trial. That result does not certify later source changes or prove uninterrupted/post-replacement private egress. The public frontend was tested through AWS and explicitly returned to DEMO without silent synthetic fallback.

[Public CI evidence](docs/results.md#public-ci-3-november-2026) · [Dated AWS summary](docs/operations/eks-cycle-2026-10-29.md) · [Architecture and ownership](docs/architecture/current-platform.md) · [Design decisions](docs/adr/README.md)

## Try it locally

Use Node **24.18.0** and npm **11.16.0**:

```sh
cd frontend
npm ci
npm run dev:demo
```

Open `http://127.0.0.1:5173/demo`. No AWS credentials or database are needed.

## Limits worth knowing

- PostgreSQL is Single-AZ. Observed node placement A/A/C is a snapshot, not guaranteed multi-AZ availability.
- NAT recovery does not provide demonstrated cross-AZ failover. Helm rollback does not undo database migrations.
- CI retains documented security exceptions; green checks do not mean zero vulnerabilities. Accessibility checks do not establish full WCAG conformance.
- Unlike an earlier final teardown, this cost-down retained protected RDS and other resources. Stopped RDS can restart automatically and retained resources still incur costs; public hosting has a finite retention window.

[Documentation map](docs/README.md) · [Development and tests](docs/development.md) · [Security boundaries](docs/security.md) · [Report a vulnerability](SECURITY.md) · [License status](docs/README.md#license-and-third-party-attribution)
