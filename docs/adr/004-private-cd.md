# ADR-004 — Private EKS CD

Status: Accepted and implemented. Live observations and their limits are recorded in [results](../results.md).

Decision: GitHub OIDC uses separated publisher/orchestrator roles with repo/ref/environment/audience restrictions. Reviewed source commit→image digest→immutable S3 bundle/VersionId/hash→fixed SSM document→private management host→namespace-scoped Helm deployer. No arbitrary script artifact or cloning main on host. Platform owns controllers, identities and network policies. The executor permits only reviewed HPA/ScaledObject additions.

Why: GitHub-hosted runners cannot connect to a private EKS endpoint. A fixed private executor preserves artifact identity and limits remote authority without another agent/control plane.

Alternatives rejected: public EKS for CI convenience, long-lived AWS credentials, unrestricted SSM shell, cluster-admin app deployments, full GitOps stack without a need.

Rollback: record before/after identity and receipt, require expected previous revision, roll back failed application release when safe. PostgreSQL migrations must remain compatible with previous app; Helm never reverses schema. Initial platform/bootstrap and GitHub protection settings are explicit operator steps.

Evidence: infra/modules/private-cd and management-host, scripts/cd, workflows, test_r4. ECR scan gate blocks publication with HIGH/CRITICAL or unavailable evidence. The post-redeploy OIDC/SSM success path was observed; live failure/replay coverage is not inferred from local tests.
