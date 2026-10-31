# Deployment and operations

[IaC reference](../architecture/infrastructure.md) Ã‚Â· [Private access](private-access.md) Ã‚Â· [Private CD](private-cd.md) Ã‚Â· [Lab cleanup](lab-cleanup.md)

This procedure describes a future authorized reconstruction. The previous environment is offline. Commands below use Bash from the repository root unless stated otherwise; replace placeholders with reviewed account outputs. They were inspected statically during the documentation update, not rerun against AWS.

## Prerequisites

- An authorized AWS account in `us-east-1`, AWS CLI v2 and temporary credentials via an explicit profile or STS session. Verify account identity before mutation. Do not transfer permanent keys or persist session credentials in files/logs.
- Terraform 1.13.4, Terragrunt 0.93.3, Python 3.13, Helm 4.2.2, kubectl 1.35.0, Git, and Docker for image builds. Private operator access also requires Session Manager plugin. The full source validator adds .NET SDK 10.0.402, Node 22 and actionlint 1.7.12.
- Account-level bootstrap roles/boundaries, `iam:PassRole` and EKS access for the intended phases. The named boundary policies in live inputs are prerequisites, not resources created by phase 1. Review [account bindings](../architecture/infrastructure.md#configuration-and-account-prerequisites).
- A private EKS/RDS network path with a bootstrap principal. Management's apps-scoped deployer identity cannot install cluster controllers or initialize database roles. Use [operator transit](private-access.md) without changing that role to cluster-admin.

```bash
python3 -m pip install -r scripts/bootstrap/requirements.txt
export AWS_PROFILE=lab-operator
export AWS_REGION=us-east-1
aws sts get-caller-identity
```

The returned account must match the intended account. Read `infra/live/dev/env.hcl` and each live stack before applying. Review region-specific AMI/addon availability, quotas, Spot capacity and NAT sizing. The checked-in account-specific IAM documents need new bindings; provisioning them is an operator responsibility.

## Backend and core infrastructure

If a verified backend already exists, preserve it. Otherwise, after reviewing its AWS mutations:

```bash
bash scripts/bootstrap-terraform-backend.sh
```

The script derives the account from STS and enforces ownership. The S3 state bucket uses `<project>-<account>-<environment>-<region>-tfstate`; the DynamoDB table uses `<project>-<account>-<environment>-terraform-locks`.

```bash
# Omit --execute to print a phase description without commands or AWS access.
python3 scripts/bootstrap/bootstrap.py --environment dev --phase 0 --execute
python3 scripts/bootstrap/bootstrap.py --environment dev --phase 1 --execute
```

Phase 1 runs `terragrunt init` and interactive `terragrunt apply` for:

```text
vpc -> nat -> s3 -> ecr -> event-encryption -> sqs -> eventbridge -> eks
-> api-gateway-authorizer-secrets -> api-gateway-authorizer
-> iam -> apigateway-core -> management -> rds
```

This applies 14 stacks; the retained `runtime-secrets` stack is read/validated only and is never applied by this cycle. Together with private-CD, observability and API integration, ownership still spans 18 stacks. The approved temporary ESO role is owned by `iam`; its exact owner output is mandatory and the original role is never a fallback. Phase 1 follows RDS's EKS/management SG dependencies. It writes `.generated/dev/environment.json`, `infra.values.yaml` and platform values from actual outputs. No secret payloads are generated into those files. Missing state fails rather than substituting mock outputs.

## Platform bootstrap and images

Establish private EKS and RDS access using the bootstrap operator identity. Supply the initial administrator email in the local process environment:

```bash
export BOOTSTRAP_ADMIN_EMAIL='operator@example.invalid'
python3 scripts/bootstrap/bootstrap.py --environment dev --phase 2 --execute
```

Use a real operator-owned email in an actual run. Phase 2 installs pinned addons, checks metrics/KEDA/ESO, applies the `observability` Terraform stack when the CloudWatch addon is absent, initializes missing secret values, installs platform/secret-sync releases and transactionally bootstraps database roles. It creates a metadata marker binding current secret versions to DB bootstrap. [Secret handling and rotation](secrets-database.md) explains the separate identities.

Apply the remaining `private-cd` stack after its prerequisites exist, with a reviewed plan and interactive approval:

```bash
(cd infra/live/dev/private-cd && terragrunt init && terragrunt apply)
```

Phase 2 also corrects the pinned CloudWatch scraper's self-metrics port and restarts that collector; it is not a secrets-only reconciliation command. If the addon already exists but its Terraform state/configuration needs reconciliation, review the `observability` stack separately rather than assuming phase 2 reapplies it.

Build each service from the committed source and push it to its generated ECR repository. For initial operator bootstrap, a conventional Docker build/push is sufficient; use the resulting digests, never `latest` in Helm. The following Bash example resolves repository URLs from the environment contract. Use a clean committed checkout. ECR tags are immutable: if a bootstrap tag already exists, verify/reuse its digest rather than overwriting it.

```bash
REGISTRY=$(python3 -c 'import json; c=json.load(open(".generated/dev/environment.json")); print(next(iter(c["repositories"].values())).split("/")[0])')
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
COMMIT=$(git rev-parse HEAD)
for SERVICE in auth shipment tracking; do
  REPOSITORY=$(python3 -c 'import json,sys; print(json.load(open(".generated/dev/environment.json"))["repositories"][sys.argv[1]])' "$SERVICE")
  docker build --platform linux/amd64 --build-arg SOURCE_COMMIT="$COMMIT" -t "$REPOSITORY:bootstrap-$COMMIT" "microservices/$SERVICE-service"
  docker push "$REPOSITORY:bootstrap-$COMMIT"
  aws ecr describe-images --repository-name "$SERVICE-service" --image-ids "imageTag=bootstrap-$COMMIT" --query 'imageDetails[0].imageDigest' --output text
done
```

Put the three returned digests in a private YAML file with exactly this shape (replace each placeholder with a real 64-digit SHA-256):

```yaml
services:
  auth:
    image:
      digest: sha256:<auth-image-hash>
  shipment:
    image:
      digest: sha256:<shipment-image-hash>
  tracking:
    image:
      digest: sha256:<tracking-image-hash>
```

This initial build is distinct from GitHub's validated build/provenance records; GitHub release publication requires its own successful build evidence. Ongoing delivery follows [Private CD](private-cd.md).

## Workloads and edge integration

```bash
python3 scripts/bootstrap/bootstrap.py --environment dev --phase 3 --images /secure/images.yaml --execute
python3 scripts/bootstrap/bootstrap.py --environment dev --phase 4 --execute
python3 scripts/bootstrap/bootstrap.py --environment dev --phase 5 --execute
python3 scripts/bootstrap/bootstrap.py --environment dev --phase 6 --execute
```

Phase 3 requires fresh ESO synchronization and the DB marker, verifies ECR digests, runs Helm migration hooks and waits for deployments. Phase 4 requires one uniquely tagged internal ALB, HTTP/80 listener and three target groups with at least two healthy targets each. Phase 5 repeats discovery and applies API integration. Phase 6 validates final outputs, VPC Link and integration wiring; it is not an authenticated business test.

```bash
kubectl get nodes
kubectl -n apps get deployments,pods,services,ingress,hpa,pdb,scaledobjects
kubectl -n apps get externalsecrets
kubectl -n kube-system get deployments
python3 scripts/bootstrap/environment.py --environment dev --final --validate .generated/dev/environment.json
```

Then exercise registration/login/refresh, anonymous and non-admin rejection, shipment creation, admin tracking creation, tracking reads and eventual Shipment status. Use controller request DTOs and the exact gateway routes, with fresh test identities. Never commit tokens, customer data or raw HTTP transcripts. The historical evidence is a result record, not a permanently running smoke endpoint.

## Routine operation and cost

Inspect rollout status, readiness, ESO conditions, outbox failure metadata, queue age/depth and CloudWatch alarms. Do not use a 401 alone as backend reachability proof. Runtime credential rotation, data recovery and Helm rollback have separate procedures. Stop temporary test pods/tunnels after use.

EKS control plane, On-Demand/Spot nodes, three NAT instances/EIPs, management EC2, RDS/storage/backups, ALB, logs, images/artifacts, data transfer and request APIs can accrue costs. Node autoscaling changes capacity and cost. Set an account budget, review current regional prices before rebuilding, and plan teardown before deployment. The previous account-wide Cost Explorer total is not a project cost measurement. [Recorded cost boundary](../results.md#cost-and-retained-resources).

After replacement, regenerate the environment contract, install/rebind effective scoped IAM, refresh GitHub variables and immutable artifact identities. Retired IDs and old approvals are not reusable. Do not re-enable delivery workflows until the new environment is ready and that action is authorized.
