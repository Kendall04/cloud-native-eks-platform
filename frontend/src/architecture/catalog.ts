export const diagrams = [
  {
    id: "platform",
    title: "Platform architecture",
    label: "Platform & services",
    tag: "01 / SYSTEM",
    description:
      "Follow authenticated requests across the public edge into private .NET services and PostgreSQL.",
    topics: [
      "API Gateway validates protected requests through a Lambda authorizer. VPC Link reaches an internal ALB; pod backends and the EKS endpoint stay private.",
      "Auth issues and validates JWTs. Shipment owns shipments; Tracking owns event history and its transactional outbox. RDS hosts separate schemas and runtime/migration identities.",
      "External Secrets synchronizes Secrets Manager values into Kubernetes Secrets. Workloads consume secretKeyRef environment variables, rather than calling ESO directly.",
    ],
    sources: [
      "docs/architecture/current-platform.md",
      "infra/modules/apigateway-core/main.tf",
      "k8s/charts/platform-secret-sync/templates/secrets.yaml",
    ],
    caveat:
      "Source-backed design reconciled with October 28–29 observations and real API/event proofs. Runtime was retired on October 29; the retained public DEMO has no API origin. This diagram does not monitor availability.",
  },
  {
    id: "networking",
    title: "Private networking",
    label: "Network & private EKS",
    tag: "02 / NETWORK",
    description:
      "Separate client ingress, management access and outbound traffic across the VPC.",
    topics: [
      "Three AZ subnet pairs have per-AZ EC2 NAT instances/EIPs. Private routes use their NAT; application traffic enters through VPC Link and the internal ALB.",
      "Management uses SSM and reaches the private Kubernetes endpoint. GitHub runners do not need network access to EKS.",
      "RDS is private and Single-AZ. On October 29, three Ready nodes were observed in A/A/C and both Auth replicas shared one node. Three-AZ subnet design does not prove workload availability in every AZ.",
    ],
    sources: [
      "docs/architecture/current-platform.md",
      "infra/modules/vpc/main.tf",
      "infra/modules/nat/launch_template.tf",
      "infra/modules/management-host/main.tf",
    ],
    caveat:
      "On October 29, one replacement in B recovered its EIP and route in 178 seconds. Private egress after replacement remains UNVERIFIED; no continuous egress or cross-AZ failover is claimed. Older B/C egress checks are separate historical evidence.",
  },
  {
    id: "event-processing",
    title: "Reliable event processing",
    label: "Event-driven flow",
    tag: "03 / EVENTS",
    description:
      "Trace Tracking → transactional outbox → EventBridge → SQS → Shipment durable inbox.",
    topics: [
      "An authorized admin tracking update commits the tracking row and outbox atomically. A leased dispatcher publishes the stable event identity, then marks publication.",
      "EventBridge routes TrackingStatusUpdated v2.0 to standard SQS. Shipment long-polls the queue, validates event identity and sequence and commits state plus durable deduplication before deleting a message.",
      "At-least-once delivery can duplicate events. Event ID deduplication and sequence checkpoints protect effects; a missing predecessor is retried. Processing and EventBridge delivery failures have separate DLQs.",
    ],
    sources: [
      "docs/operations/events.md",
      "microservices/tracking-service/src/TrackingService.Infrastructure/Messaging/OutboxDispatcher.cs",
      "microservices/shipment-service/src/ShipmentService.Infrastructure/Services/TrackingEventProcessor.cs",
    ],
    caveat:
      "This is a designed successful path, not a live trace or an exactly-once transport guarantee. Two event sequences were published and persisted on October 29; broader failure-case evidence is dated October 24. The synthetic DEMO does not run AWS event workers.",
  },
  {
    id: "private-cd",
    title: "Private delivery",
    label: "CI/CD & private delivery",
    tag: "04 / DELIVERY",
    description:
      "Promote immutable artifacts while keeping the EKS API private.",
    topics: [
      "CI V2 runs AWS-free validation on pull requests and branch pushes. Manual Build validates, publishes immutable images and scans their exact digests before it can succeed. Create Release and Deploy are separate manual workflows, demonstrated on October 29. This page does not monitor workflow enablement.",
      "OIDC roles separate publishing from orchestration. ECR digests and versioned S3 bundles bind all three services to the same source commit; SHA256 and exact artifact identity are verified.",
      "SSM invokes a restricted executor on Management. Executor 1.4.0 checks replay state, locks, chart pins and Helm revision, runs migrations/rollout and writes durable receipts. Rollback is guarded.",
    ],
    sources: [
      "docs/operations/private-cd.md",
      ".github/workflows/validate.yml",
      "infra/modules/management-host/deployer",
    ],
    caveat:
      "PROVEN on October 29: manual v2.0.8 private delivery reached Helm revision 4 after a prior strict-smoke failure and verified automatic rollback. Readiness gates matched new healthy ALB targets. Helm rollback does not revert PostgreSQL migrations.",
  },
  {
    id: "security",
    title: "Security & Trust Boundaries",
    label: "Security & trust",
    tag: "05 / TRUST",
    description:
      "Understand who trusts whom: user identity, workload credentials and private delivery authority.",
    topics: [
      "The REQUEST authorizer authenticates protected routes. Services bind the trusted subject to Auth's current profile, then enforce active-user, role and resource ownership checks.",
      "Kubernetes service accounts federate through scoped IRSA roles. ESO reads approved secrets; workloads and migration Jobs use separate PostgreSQL credentials and schema permissions.",
      "Publisher, orchestrator and management have separate responsibilities. Immutable artifacts, fixed SSM contracts and expected revisions constrain private execution; they do not certify production security.",
    ],
    sources: [
      "docs/security.md",
      "infra/modules/private-cd/main.tf",
      "microservices/shipment-service/src/ShipmentService.Api/Infrastructure/CurrentProfileClient.cs",
    ],
    caveat:
      "DECLARED trust contracts with dated October 28–29 evidence. Internal HTTP is not mTLS; RDS is Single-AZ. Runtime was retired on October 29. No live health, uninterrupted availability or compliance certification is implied.",
  },
] as const;
export type DiagramId = (typeof diagrams)[number]["id"];
export const technicalPages = [
  { id: "scaling", label: "Kubernetes & scaling" },
  { id: "evidence", label: "Validation evidence" },
] as const;
export const liveChecks = [
  "The October 29 public AWS-to-DEMO transition was demonstrated: the previous AWS tab showed honest unavailability and reload selected DEMO without retaining authentication.",
  "Hosting A/B/A configuration selection is not two distinct authenticated web-source releases.",
  "Selected event and scaling samples do not prove arbitrary gap recovery, AZ failure behavior or an SLA.",
  "Manual Build, Release and private Deploy were demonstrated on October 29; an authentic Dependabot security-update PR remains a separate repository task.",
  "TLS/CSP tradeoffs, residual findings and eventual physical key deletion remain explicit limits.",
];
