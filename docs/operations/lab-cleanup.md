# Lab cleanup from Windows

**Historical inventory warning:** the absence/disposition statements and the 31 October RDS restart estimate below belong to the 27 October snapshot. The later 29 October cost-down retained RDS stopped and protected; its recorded stop was 29 October at 20:14:57 Costa Rica, with automatic restart expected 5 November at 20:14:57. See [post-cycle rebuild prerequisites](post-cycle-rebuild.md) for the intentionally empty DB ingress and required explicit restoration. No current AWS status is inferred from this source; review actual identities and each saved plan in any newly authorized operational session.

Manual procedure for `main` at `354a5e42`, without the teardown framework. **Execute mutations only in a separately authorized cleanup session**, one step at a time. Freeze CI/CD, load, migrations and writers. Preserve old journals/approvals unchanged.

## Scope already established

Use the 27 October 2026 inventory and 18 states (167 registered identities present, 19 absent). Recheck each target before mutation; no new full audit is needed.

**Routine cost-down** retires selected trial resources while retaining the backend, historical secrets/access and separate hosting. RDS can remain retained; then skip its preparation/deletion and retain its required SG/network dependencies, recording storage charges and automatic restart risk. **Complete deletion** is a separate scope: every retained object needs an explicit final disposition, with the backend removed last after independent evidence and all dependent states are settled. Do not claim complete deletion from this routine's retained-resource outcome.

| Disposition | Resources |
| --- | --- |
| Keep | Backend `cloud-native-platform-341936017254-dev-us-east-1-tfstate`, its versions and DynamoDB `cloud-native-platform-341936017254-dev-terraform-locks`; the ten historical application/authorizer secrets and their original ESO role/policy; shared GitHub OIDC, retained EKS OIDC, operator boundaries and AWS-managed keys; portfolio S3/CloudFront and unrelated projects. Leave `runtime-secrets` and `api-gateway-authorizer-secrets` states intact. |
| Eligible after review | RDS `cloud-native-platform-dev-postgres` and its backups/master secret; project API/VPC Link, Lambda, three target groups, workload/CD IAM, queues/events/event CMK, network, artifacts/logs buckets, three ECR repositories and telemetry. DB/backup purge requires a data-loss decision. |
| Already absent | EKS, its node groups/addons, management/NAT EC2, ASGs, EIP, NAT gateways, EBS volumes/snapshots and VPC endpoints. Let a destroy plan observe this drift; never recreate them to clean up. |

RDS was stopped/protected, with 20 GiB, one automated snapshot and restart due **31 October 2026, 21:42 Costa Rica**. Three private routes were blackholes; two API integrations referenced the deleted listener. Leave the five already-pending CMK deletion schedules unchanged. Retained storage/hosting remain billable.

## 1. Session, private backups and command pattern

Use existing PowerShell **7.4+**, AWS CLI v2, Terraform **1.13.4**, Terragrunt **0.93.3** and locked providers. Helm **4.2.2**/kubectl are needed only with live EKS. Use the original checkout and an **existing protected directory outside Git** for sensitive state/plans. Terragrunt may populate its normal ignored cache; no project copy, upgrade or backend bootstrap.

```powershell
$ErrorActionPreference = 'Stop'
$Repo = 'C:\proyectos\cloud-native-platform-eks'
Set-Location $Repo
$env:AWS_PROFILE = 'cnp-cert-dev'; $env:AWS_REGION = 'us-east-1'
$env:AWS_DEFAULT_REGION = 'us-east-1'; $env:AWS_PAGER = ''
$env:TG_DEPENDENCY_FETCH_OUTPUT_FROM_STATE = 'true'
function Check { if ($LASTEXITCODE -ne 0) { throw "Native command failed: $LASTEXITCODE" } }
$Account = aws sts get-caller-identity --query Account --output text; Check
if ($Account -ne '341936017254') { throw 'Wrong account' }
$Private = (Resolve-Path (Read-Host 'Existing private directory outside Git')).Path
if ($Private -eq $Repo -or $Private.StartsWith("$Repo\", [StringComparison]::OrdinalIgnoreCase)) { throw 'Private files must be outside Git' }
$AllowedSids = @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value, 'S-1-5-18', 'S-1-5-32-544')
$Rules = (Get-Acl -LiteralPath $Private).GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])
if (@($Rules | Where-Object { $_.AccessControlType -eq 'Allow' -and $_.IdentityReference.Value -notin $AllowedSids }).Count) { throw 'Use a private directory accessible only to this operator, SYSTEM and Administrators' }
$Run = [Guid]::NewGuid().ToString('N')
function TG([string]$Stack, [string[]]$TfArgs) {
    & terragrunt --working-dir "$Repo\infra\live\dev\$Stack" run --tf-path terraform --disable-bucket-update --backend-require-bootstrap --no-auto-retry -- @TfArgs
    Check
}
$Stacks = 'vpc','nat','s3','ecr','event-encryption','sqs','eventbridge','rds','eks','api-gateway-authorizer-secrets','runtime-secrets','api-gateway-authorizer','iam','apigateway-core','management','apigateway-integration','private-cd','observability'
$Backend = 'cloud-native-platform-341936017254-dev-us-east-1-tfstate'
foreach ($s in $Stacks) {
    $key = "dev/$s/terraform.tfstate"
    $v = aws s3api head-object --bucket $Backend --key $key --query VersionId --output text; Check
    aws s3api get-object --bucket $Backend --key $key --version-id $v "$Private\$Run-$s.tfstate" > $null; Check
}
```

The wrapper syntax was checked against installed Terragrunt 0.93.3 help and with a recording-only command substitute; no Terraform/AWS command was executed. The ACL check rejects other allow entries rather than changing permissions; choose an already protected directory if it fails.

Before changing each stack, use this pattern; **do not put the ordered steps into an unattended loop**:

```powershell
$Stack = 'apigateway-integration' # Select the next row below.
$Plan = "$Private\$Run-$Stack-destroy.tfplan"
TG $Stack @('plan','-destroy','-lock-timeout=60s',"-out=$Plan")
TG $Stack @('show','-no-color',$Plan) # Sensitive: review locally.
# Only after reviewing this exact saved plan:
TG $Stack @('apply','-lock-timeout=60s',$Plan)
TG $Stack @('state','list')
```

Accept only intended deletes/no-ops/reads; reject creates/replacements and retained/shared targets. Destroy planning refreshes manually removed resources. Never use `-refresh=false`, `state rm`, force-unlock, `run --all destroy` or finalizer removal. Preserve dependency outputs until their last consumer finishes. Missing/mocked outputs require recovering real bindings from versioned state, not applying mocks. After interruption, inspect native state and replan; never blindly replay.

## 2. Order and completion barriers

| Step | Owner/action | Required before continuing |
| --- | --- | --- |
| 1 | `apigateway-integration` | Routes/integrations removed, including dangling listener references. |
| 2 | Kubernetes owners, **only if EKS exists** | In the existing private context: inspect `helm list -A` and `kubectl -n apps get ingress,jobs`; stop active jobs/writers. Delete the exact project Ingress with `kubectl -n apps delete ingress platform-services --wait=true --timeout=10m`. Keep LBC until its ALB, target groups and ENIs are gone. Then `helm uninstall platform-services -n apps --wait`, `helm uninstall platform-secret-sync -n apps --wait`, and `helm uninstall platform-bootstrap -n apps --wait`. Observe project custom-resource consumers gone; after observability below, uninstall `cluster-addons -n kube-system --wait`. Do not delete AWS-managed CNI/core addons by Helm. If EKS is absent, skip Kubernetes and handle proven orphan target groups below. |
| 3 | `observability` | EKS observability addon and project telemetry retired; keep private access/controllers needed above. |
| 4 | **Only if deleting RDS:** preparation below, then `rds` | DB absent, its master secret and backup disposition checked. Otherwise retain DB/SG/network dependencies and omit their deletion. |
| 5 | `private-cd`, then `management` | No deployment/SSM work active; Kubernetes cleanup complete before losing transit. Shared GitHub OIDC must remain. |
| 6 | `iam`, then `eks` | Workload consumers gone. Reject deletion of the retained issuer/original ESO identities; an issuer outside state must not be adopted/deleted. Preserve declared retained identities if a later cycle puts them into a stack. |
| 7 | `apigateway-core`, then `api-gateway-authorizer` | API/VPC Link gone; wait for service-owned ENIs before SG/network cleanup. |
| 8 | `eventbridge`, then `sqs`, then `event-encryption` | Delivery/writers stopped; queues drained or explicitly discarded. Event key has no retained/new-trial consumers; Terraform may schedule its 30-day deletion. |
| 9 | `nat`, then `vpc` | Follow NAT branch below. No foreign ENI/SG consumer or shared subnet. Route-table deletion removes old blackholes; do not repair routes to deploy new NAT. |
| 10 | Empty only approved artifacts/logs buckets and ECR images below; then `s3`, `ecr` | CD and management gone. Backend and portfolio excluded. |

**RDS, only at its deletion step:** the proposed choice is no final snapshot and deletion of automated backups; obtain execution-time data-loss approval. Require the original generation below. Do not start or unprotect a DB being retained. Starting a stopped DB for deletion preparation temporarily incurs compute cost.

```powershell
$Db = 'cloud-native-platform-dev-postgres'
$Observed = aws rds describe-db-instances --db-instance-identifier $Db --query 'DBInstances[0].{Generation:DbiResourceId,Status:DBInstanceStatus}' --output json | ConvertFrom-Json; Check
if ($Observed.Generation -ne 'db-RCFKI3BK5VNW4OFBOBGD652PMY') { throw 'DB generation changed' }
if ($Observed.Status -eq 'stopped') {
    aws rds start-db-instance --db-instance-identifier $Db > $null; Check
    aws rds wait db-instance-available --db-instance-identifier $Db; Check
} elseif ($Observed.Status -ne 'available') { throw 'Wait for a stable DB state' }
@{ teardown = @{ decision='PURGE_DATABASE_EVIDENCE'; delete_automated_backups=$true } } | ConvertTo-Json -Depth 4 | Set-Content "$Private\$Run-rds.tfvars.json" -Encoding utf8NoBOM
$Prep = "$Private\$Run-rds-prepare.tfplan"
TG rds @('plan','-target=aws_db_instance.this',"-var-file=$Private\$Run-rds.tfvars.json","-out=$Prep")
TG rds @('show','-no-color',$Prep)
# Accept only the same DB's deletion_protection, skip_final_snapshot,
# final_snapshot_identifier and delete_automated_backups changes. No replacement.
TG rds @('apply',$Prep)
aws rds describe-db-instances --db-instance-identifier $Db --query 'DBInstances[0].DeletionProtection'; Check
# Require false; then use the destroy pattern, with the same -var-file on plan.
```

The existing `teardown` input needs no module edit. Stop if preparation fails; never broaden the apply. References: [RDS modification](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.DBInstance.Modifying.html), [deletion/backups](https://docs.aws.amazon.com/cli/latest/reference/rds/delete-db-instance.html).

## 3. NAT HA and exact residuals

**Current NAT:** serial 38 records absent legacy EC2/EIP. Use destroy planning against `main` for surviving SG/IAM; never apply the ASG migration just to clean up.

**Only for a later live HA generation:** after egress consumers retire, plan/apply `nat` with `-var=recovery_enabled=false` (normal saved plan). Accept only CONTROL/EventBridge/Lambda inhibition and ASG capacity zero. Read CONTROL/slot records, Lambda and ASG activity; settle uncertain ATTEMPT effects and export evidence. Zero capacity/concurrency alone is insufficient. Keep `aws_dynamodb_table.recovery[0]`, `aws_dynamodb_table_item.control[0]`, `aws_sqs_queue.failures[0]`. List addresses with `TG nat @('state','list')`; for this partial retirement, add explicit `-target=<address>` arguments for each reviewed non-retained address to a saved destroy plan. Reject deletion of the three retained addresses. Never remove `prevent_destroy` or clear journals; record these retentions.

These protected HA resources need an owner and final disposition (retention deadline or deliberate indefinite retention). Complete deletion requires a separately reviewed owner change and saved plan for their protections/data; this guide does not disable guards or silently leave them behind.

**CLI fallback:** require owner absence/failure and exact native ID, tags, VPC and references proving lab ownership. Never directly delete service-owned ENIs. For the three known orphan groups:

```powershell
aws elbv2 describe-target-groups --names k8s-apps-authserv-3064804a40 k8s-apps-shipment-0d020db898 k8s-apps-tracking-88edb50264; Check
$Arn = Read-Host 'Exact reviewed target group ARN'
aws elbv2 describe-tags --resource-arns $Arn; Check
aws elbv2 describe-target-health --target-group-arn $Arn; Check
# Require matching project/cluster/VPC, no owning ALB/listener or live controller:
aws elbv2 delete-target-group --target-group-arn $Arn; Check
```

Remove exact bucket entries/image digests individually:

```powershell
$Bucket = Read-Host 'Exact artifacts or logs bucket (never backend/portfolio)'
if ($Bucket -notin @('cloud-native-platform-341936017254-dev-us-east-1-artifacts','cloud-native-platform-341936017254-dev-us-east-1-logs')) { throw 'Bucket outside cleanup scope' }
aws s3api list-object-versions --bucket $Bucket; Check
aws s3api list-multipart-uploads --bucket $Bucket; Check
aws s3api delete-object --bucket $Bucket --key '<reviewed-key>' --version-id '<reviewed-version-or-delete-marker>'; Check
# Only if an exact unfinished upload was listed:
aws s3api abort-multipart-upload --bucket $Bucket --key '<reviewed-key>' --upload-id '<reviewed-upload-id>'; Check
# Repeat for auth-service, shipment-service, tracking-service after ownership review:
aws ecr describe-images --repository-name auth-service; Check
aws ecr batch-delete-image --repository-name auth-service --image-ids imageDigest='<reviewed-digest>'; Check
```

Require S3 versions, delete markers and uploads empty before owner destroy; inspect per-item errors. After DB absence, review/delete its leftover log with `aws logs delete-log-group --log-group-name /aws/rds/instance/cloud-native-platform-dev-postgres/postgresql`. Manual snapshots require reviewed `aws rds delete-db-snapshot --db-snapshot-identifier <exact-id>`; retained automated backups use `aws rds delete-db-instance-automated-backup --dbi-resource-id <exact-generation>`. Unexpected EC2/EIP/volume/NAT/SG resources require exact ownership review before native deletion. Investigate `DependencyViolation`; never force it.

## 4. Close with targeted absence and retention checks

Check each owner's native IDs and `state list` before dependencies disappear. Finally reread the 18 S3 objects as in step 1 (new `$Run`): empty dependencies may prevent Terragrunt parsing. Only the two secret states and declared HA evidence may remain nonempty. Empty state/exit zero is not native absence.

```powershell
$Vpc = 'vpc-05a8ec8d7de5a8271'
aws eks list-clusters; Check
aws ec2 describe-instances --filters "Name=vpc-id,Values=$Vpc" --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name}'; Check
aws autoscaling describe-auto-scaling-groups --query 'AutoScalingGroups[].{Name:AutoScalingGroupName,Desired:DesiredCapacity,Members:Instances}'; Check
aws ec2 describe-nat-gateways --filter "Name=vpc-id,Values=$Vpc"; Check
aws ec2 describe-addresses; Check
aws ec2 describe-volumes; Check
aws ec2 describe-snapshots --owner-ids self; Check
aws rds describe-db-instances --query 'DBInstances[].{Id:DBInstanceIdentifier,Status:DBInstanceStatus}'; Check
aws rds describe-db-snapshots --db-instance-identifier cloud-native-platform-dev-postgres; Check
aws rds describe-db-instance-automated-backups --dbi-resource-id db-RCFKI3BK5VNW4OFBOBGD652PMY; Check
aws elbv2 describe-load-balancers; Check
aws elbv2 describe-target-groups; Check
```

Require trial compute/NAT/EIP/EBS/RDS absent and backups purged or explicitly retained. Re-read the audit's exact API/VPC Link, Lambda, queues, eight log groups, seven alarms, dashboard and three ECR repositories: require absence or named retention. Inspect ENIs/endpoints if VPC retirement blocks. Regional lists also return foreign resources: preserve them. Confirm backend, portfolio, secrets/ESO/OIDC/boundaries unchanged. Report pending deletion windows, retained charges and unknowns explicitly; unknowns mean incomplete cleanup.
