# Cloud Native Platform EKS

[![Validate](https://github.com/Kendall04/cloud-native-eks-platform/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/Kendall04/cloud-native-eks-platform/actions/workflows/validate.yml)

A production-like engineering portfolio demonstrating a private AWS platform for three .NET 10 logistics microservices. **Logistics Platform Demo** makes the application explorable; **Architecture Explorer** explains the design and its tradeoffs.

[Open Logistics Demo](https://d3ujivegzs1gn7.cloudfront.net/demo) · [Open Architecture Explorer](https://d3ujivegzs1gn7.cloudfront.net/architecture) · [Documentation](docs/README.md)

## What this project demonstrates

- **Private workloads:** EKS, Auth/Shipment/Tracking, PostgreSQL 15.18 and scoped secret delivery through External Secrets.
- **Public ingress:** API Gateway with a Lambda REQUEST JWT authorizer, VPC Link and an internal ALB. Services verify current identity, roles and resource ownership.
- **Reliable events:** Tracking's transactional outbox → EventBridge → standard SQS → Shipment's durable inbox, with deduplication and sequence handling.
- **Private delivery:** manual Build, Release and Deploy through GitHub OIDC, immutable artifacts, SSM and Helm; GitHub does not connect directly to Kubernetes.
- **Reproducible infrastructure:** Terraform/Terragrunt, pinned dependencies, contract tests and separate ownership for runtime and static hosting.

## Lifecycle completed

Real AWS trials on **28–29 October 2026** demonstrated authentication and persisted business operations, asynchronous events, private deployment, automatic rollback after a failed smoke, and ALB Pod Readiness Gates. One NAT replacement restored its EIP and route in **178 seconds**.

The lab is offline after the 29 October cost-down; AWS delivery workflows are disabled. Unlike an earlier final teardown, this cycle intentionally retained protected RDS, data, network dependencies, identities, artifacts and state. RDS was last observed stopped; automatic restart and residual storage charges require separate operational attention.

The public **DEMO — Synthetic Data** edition was published on 30 October. It uses no backend; CloudFront has no API forwarding. The AWS edition was exercised separately and explicitly returned to DEMO. These are dated observations, not live telemetry or an indefinite hosting commitment.

[Results, evidence and limits](docs/results.md) · [Architecture and service ownership](docs/architecture/current-platform.md)

## Try it locally

Use Node **24.18.0** and npm **11.16.0**, from the repository root:

```sh
cd frontend
npm ci
npm run dev:demo
```

Open `http://127.0.0.1:5173/demo`. No AWS credentials or database are required. The Explorer includes five Archify 3.1.0 diagrams, guided reading and a textual alternative, including **Security & Trust Boundaries**.

[Frontend setup](frontend/README.md) · [Development and tests](docs/development.md) · [Security](docs/security.md) · [Architecture decisions](docs/adr/README.md)

## Important limits

RDS is Single-AZ. NAT recovery did not prove continuous or post-replacement private egress, nor cross-AZ failover. Helm rollback does not reverse database migrations. Automated accessibility checks do not establish complete WCAG conformance. This is a tested demonstration, not a production certification or SLA.
