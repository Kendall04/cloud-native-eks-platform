# Architecture

[Overview](../../README.md) · [IaC](infrastructure.md) · [Security](../security.md) · [Observed results](../results.md)

## Request and data flow

The only complete live environment definition is `dev` in `us-east-1`. The HTTP API is public; its backends and Kubernetes control-plane endpoint are private. API Gateway uses a Lambda REQUEST authorizer for protected routes and connects through a VPC Link to an internal HTTP ALB. The Load Balancer Controller registers pod IP targets on port 8080.

| Service | Responsibility | Dependencies |
| --- | --- | --- |
| [Auth](../../microservices/auth-service) | Registration, login, refresh-token rotation, JWT issuance and user/admin endpoints | PostgreSQL `auth` schema |
| [Tracking](../../microservices/tracking-service) | Tracking timelines, admin event creation and transactional outbox dispatch | `tracking` schema, Shipment internal lookup, EventBridge |
| [Shipment](../../microservices/shipment-service) | Customer shipment API and SQS event consumption in one Deployment | `shipment` schema, SQS and event KMS key |

Auth uses ASP.NET Identity and HS256 JWTs. API Gateway replaces identity headers with authorizer context; Shipment/Tracking validate the proxy shared secret and enforce ownership/Admin policies. Current local source additionally requires Shipment/Tracking to send the original bearer to Auth's private `/auth/me` on each protected request and bind current identity/roles to the gateway attestation; see [ADR-005](../adr/005-current-profile-authorization.md). The [24 October matrix](../operations/eks-acceptance-2026-10-24.md) records scoped live enforcement of these checks, NetworkPolicy edges and TTL0; that runtime is now offline. Auth validates its JWTs itself. Internal Tracking→Shipment lookup uses a separate shared secret. These internal hops use HTTP, not mTLS.

Public routes are explicitly listed in [integration inputs](../../infra/live/dev/apigateway-integration/terragrunt.hcl) and checked by [the HTTP contract validator](../../scripts/validation/validate_r1.py). Registration/login/refresh are public. Shipment and tracking reads/writes require authentication; `/admin/tracking-events` requires Admin. Application controllers contain additional operations; their existence does not automatically expose them at the gateway. `/internal/*`, health and Swagger are not public gateway routes.

All three services share one RDS PostgreSQL instance with separate schemas and runtime/migration users. Readiness checks database connectivity; liveness checks process health. EF migrations run through Helm hook Jobs using migration identities. The application runtime does not bootstrap schemas or use the RDS master credential.

## Event path

```mermaid
sequenceDiagram
  participant Caller as Admin client
  participant T as Tracking
  participant DB as PostgreSQL
  participant EB as EventBridge
  participant Q as SQS
  participant S as Shipment
  Caller->>T: Authenticated tracking update
  T->>DB: Commit TrackingEvent + OutboxMessage
  T-->>Caller: Created
  T->>DB: Dispatcher claims leased outbox row
  T->>EB: PutEvents (stable domain EventId)
  EB-->>T: Publication result
  T->>DB: Mark published after success
  EB->>Q: TrackingStatusUpdated v2.0 (detail only)
  S->>Q: ReceiveMessage (long poll)
  Q-->>S: Event batch
  S->>DB: Lock shipment, check EventId/sequence, commit state + inbox
  S->>Q: Delete after durable success
```

The sequence shows a successful path; publication-marker persistence and downstream delivery are independent and can race.

Only `TrackingStatusUpdated` v2.0 is active. A publish-before-marker crash may duplicate an event; durable `ProcessedEvents` deduplication protects the business effect. Sequence N+2 arriving before N+1 is retried without advancing the checkpoint. The source queue is standard SQS, so ordering comes from application state, not transport guarantees. Processing failures and EventBridge delivery failures use separate DLQs. [Recovery](../operations/events.md) preserves event identity and repairs predecessors before replaying successors.

There is no active analytics worker or notification target. The [notification Lambda](../../lambdas/notification-lambda) is an inactive example, preserved as source rather than represented as deployed functionality.

## Network and Kubernetes placement

```mermaid
flowchart TB
  External[Internet and regional AWS APIs]
  Clients[Clients] -->|HTTPS| API[API Gateway HTTP API]
  subgraph VPC["VPC 10.0.0.0/16"]
    IGW[Internet gateway]
    subgraph A[us-east-1a]
      PA["Public 10.0.0.0/20<br/>NAT ASG A (0/1) + EIP"]
      QA["Private 10.0.128.0/20<br/>Management; no observed EKS nodes"]
      QA -->|Default route| PA
    end
    subgraph B[us-east-1b]
      PB["Public 10.0.16.0/20<br/>NAT ASG B (0/1) + EIP"]
      QB["Private 10.0.144.0/20<br/>Observed EKS capacity"]
      QB -->|Default route| PB
    end
    subgraph C[us-east-1c]
      PC["Public 10.0.32.0/20<br/>NAT ASG C (0/1) + EIP"]
      QC["Private 10.0.160.0/20<br/>Observed EKS capacity"]
      QC -->|Default route| PC
    end
    Endpoint[Private EKS endpoint]
    QA -->|Operator transit / CD| Endpoint
    QB & QC --> Endpoint
    Groups["API On-Demand + worker Spot groups"] -. observed capacity .-> QB & QC
    Link[VPC Link ENIs] -->|HTTP 80| ALB[Internal ALB]
    ALB -->|Pod targets 8080| QB & QC
    DB["Single-AZ RDS<br/>Subnet group spans A/B/C"]
    QB & QC -->|5432 TLS| DB
    QA -->|Operator DB transit 5432| DB
    PA & PB & PC --> IGW
  end
  API --> Link
  IGW --> External
```

The diagram separates declared subnet eligibility from observed node placement. Both managed groups use private subnets across all three AZs, but the verified run placed nodes in B/C. Management uses the first private subnet (A). RDS is Single-AZ; its subnet group spanning AZs does not make the database Multi-AZ. The DB's physical AZ is intentionally unspecified.

The declared NAT stack uses three single-AZ ASGs, each with one NAT EC2 when enabled and zero capacity while paused. A fenced launch callback verifies bootstrap and restores SourceDestCheck, the slot EIP and its private default route. Dev activation defaults to off. Same-AZ replacement is locally tested source, not an AWS recovery result; continuous forwarding repair and cross-AZ failover are not configured. See [NAT recovery and migration](../operations/nat-recovery.md). This lowers lab cost while adding operational responsibility. The code defaults to `t3.micro`; historical operations included an OOM/resize incident. Review sizing before rebuilding; the default is not a demonstrated capacity guarantee.

The API group defaults to two On-Demand `t3.large` nodes (range 2–6), and the worker group to one Spot `t3.large` (range 1–10). Workload labels do not imply hard service placement: chart node selectors are empty and spread is soft. Root launch templates specify encrypted 50 GiB gp3 disks with IMDSv2. See [EKS source](../../infra/modules/eks).

## Controllers and ownership

| Owner | Resources |
| --- | --- |
| Terraform/Terragrunt | VPC/NAT, EKS/node groups/core addons, RDS, messaging, identity, secret containers, ECR/S3, API/VPC Link/security groups, management, CD and observability |
| `cluster-addons` Helm release | LBC, Cluster Autoscaler, Metrics Server, KEDA and ESO |
| `platform-bootstrap` release | Service accounts, RBAC, RDS CA, SecretStore, KEDA auth and NetworkPolicies |
| `platform-secret-sync` release | ExternalSecrets managed by ESO |
| `platform-services` release | Three Deployments/Services/migration Jobs/PDBs, Auth/Tracking HPA, Shipment ScaledObject and Ingress |
| AWS LBC | Internal ALB, listener, target groups, shared backend SG and target rules |

Terraform owns the frontend ALB SG, accepting HTTP only from the VPC Link SG. It discovers the LBC-created listener after workloads are healthy; it does not also own the load balancer. The separate releases keep the apps-scoped CD executor from installing platform identities/controllers. [Bootstrap ordering](../operations/deployment.md) handles this dependency.

JSON logs and EMF metrics feed CloudWatch alongside the managed observability addon, dashboard and alarms. CPU HPA controls Auth/Tracking (2–4); SQS KEDA controls Shipment (2–6); Cluster Autoscaler controls node capacity. PDBs and soft AZ/node spread reduce selected disruptions. Their presence is not proof of end-to-end HA. See [limits](../results.md#limitations).
