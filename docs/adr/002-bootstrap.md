# ADR-002 — ALB/API Gateway bootstrap

Status: Accepted and implemented. Live observations and their limits are recorded in [results](../results.md).

Decision: Terraform core → operator addons/platform → app Ingress → LBC creates ALB/listener → unique tag/VPC/scheme/listener/health discovery gate → Terraform API integration → final generated contract. Terraform owns frontend ALB SG and VPC Link SG; LBC owns ALB, listener, target groups and backend ingress rules.

Why: Kubernetes owns a dynamically reconciled resource consumed by AWS IaC. Explicit phases are clearer than cyclic providers or manual ARN copy/paste.

Alternatives rejected: hardcoded listener ARN/SG, Terraform simultaneously owning the LBC ALB, deployment-time arbitrary discovery scripts accepting ambiguous matches.

Evidence: scripts/bootstrap, infra/modules/apigateway-integration and its mock tests, platform-services ingress. Validation: validate_r2, tag ambiguity/wrong-VPC rejection. The completed reconstruction exercised this ordering; arbitrary replacement scenarios remain bounded by the discovery guards.
