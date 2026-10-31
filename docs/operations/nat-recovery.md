# Per-AZ NAT instance recovery

[Architecture](../architecture/current-platform.md) | [IaC](../architecture/infrastructure.md)

This is locally tested source, not a deployed recovery or HA result. Dev admission
defaults to **off**. No AWS changes or state reconciliation accompanied this
implementation. The existing private CD and application pipelines are unchanged.
The normal bootstrap's core-creation phase now rejects inhibited instance-mode
NAT before AWS commands, output reads or Terragrunt execution. Read-only phase 0
remains available. This local preflight is not cloud-side access enforcement.

## Declared topology and ownership

`nat-egress` declares one ASG in each selected public subnet, using the existing
`nat` child for its stable EIP, security group, instance profile and launch template.
Dev selects three AZs. The shared-private-table variant selects one slot instead;
the controller supports one to three distinct slots, not fixed A/B constants.
With admission on, each ASG has min/desired/max **1**, EC2 health checks and a
terminate-before-launch maintenance policy. With admission off all three values
are zero. Templates pin a numeric version, reviewed AMI, `t3.micro`, IMDSv2,
standard CPU credits and an encrypted 8 GiB gp3 delete-on-termination root disk.
No scaling policy, warm pool or automatic template refresh is installed.

Terraform owns stable allocations, launch primitives, ASGs and controller
configuration. The recovery controller exclusively owns instance-mode EIP
associations, SourceDestCheck and private IPv4 default-route targets. Terraform's
`aws_route.default` remains only for gateway mode; two writers must never manage
the same instance-mode route. `nat_asg_names` replaces static member identity;
deprecated `nat_instance_ids` deliberately returns an empty map. Discover members
from ASG/EC2 rather than inventing permanent instance IDs in Terraform outputs.

## Launch-to-recovery path

ASG creation depends on the installed EventBridge target, Lambda permission,
async failure destination and durable admission control. The exact regional,
account-bound `aws.autoscaling` launch-success rule identifies an allowed ASG
and event instance. It cannot enroll a new instance or supply network targets.
The callback resolves that exact group's sole InService/Healthy member and
independently checks EC2/ENI attachment, VPC/subnet/AZ, tags, SG, profile, AMI,
numeric template version and both template/actual user-data hashes.

Guest bootstrap installs iptables under a 180-second command timeout, persists
forwarding/MASQUERADE, reads back sysctl/rules/service, and emits one instance-bound
`CNP_NAT_BOOTSTRAP_V1` console marker. IMDSv2 tokens are never traced or retained.
The callback waits at most 12 readiness observations/120 seconds; EC2 status
checks and a correctly timestamped, nonduplicate success marker are required.
A launch event and EC2 `running` alone are insufficient.

Readiness failure before effects does not create a pending journal record or
replace an earlier READY record. A duplicate after bootstrap becomes ready, or a
healthy replacement after an unready member, can proceed without journal cleanup.
Exhausted delivery retries still require operator review; this is not unbounded
automatic replay.

The callback then disables SourceDestCheck, associates the fixed EIP, and creates
or replaces only the slot's private `0.0.0.0/0` route. Each effect requires fresh
membership/admission and independent readback. Unrelated routes are preserved;
foreign EIP attachments/default next hops are rejected before the first effect.

## Serialization, duplicates and uncertainty

One Lambda with reserved concurrency one serializes all slots; simultaneous
three-AZ launches can therefore queue. Each slot has a conditional-revision
DynamoDB record. CONTROL contains the reviewed configuration hash and enabled
flag; the Lambda can read CONTROL but can write only its fixed slot keys.
There is no lease, TTL takeover, delete-record or force-unlock operation.

The stable operation identity binds configuration generation, instance, ENI and
launch time. Different delivery IDs for the same current member are idempotent.
Events for old members cannot move networking back to the old ENI. A verified
READY record admits a replacement and its previous verified ENI. Configuration
generation changes or an unsettled previous member require separate review.

Every mutation records ATTEMPT before its single SDK call, ACK after the response,
then network readback. An acknowledged effect can be reconciled by reads without
resending it. A transport timeout, process loss or failed ACK write can leave
ATTEMPT: subsequent automatic calls stop even if the network happens to match.
The original request might still complete late. Do not clear the record, change
event IDs or create a fresh operation to bypass that uncertainty.

Conditional journal writes, reserved concurrency and repeated membership checks
contain races; they are **not an atomic fence enforced by EC2**. ASG membership
can change after the final check while an EC2 call is in flight. The callback
stops on changed membership and retains the unresolved record, blocking further
automatic effects until the exact outstanding action is independently settled.

Delivery retries are bounded to three/900 seconds; Lambda function-error retries
to one/900 seconds. Event age is checked again by the runtime. Delivery/execution
failures go to one encrypted, 14-day SQS evidence queue, with no consumer or
automatic replay. Journal/table deletion protection and queue `prevent_destroy`
retain unresolved evidence. Two CloudWatch alarms expose handler errors and queue
backlog; no subscription or delivered-notification claim is made. Destination
delivery can itself fail: absence of queue messages does not prove no failures.

IAM permits exact EIP allocations and route tables, subnet/tag-constrained ENIs,
tagged NAT instances with only the SourceDestCheck attribute, fixed journal keys,
own logs and failure delivery. It grants no SSM/SSH, termination, launch, ASG
update, PassRole, record deletion or queue-consumption authority. IAM efficacy
and native event delivery still require a separately authorized AWS test.

## Replacement versus AZ or forwarding failures

ASG EC2 health replaces a terminated or EC2-unhealthy member **inside its AZ**.
No termination-event callback is needed to restore desired capacity: ASG does
that natively, and the subsequent launch-success callback configures the new ENI.
Launch callbacks restore its configuration. The guest bootstrap marker proves
configuration at launch, not continuing forwarding. A later iptables failure,
packet loss or useful private-subnet egress failure is not monitored here and
does not automatically mark a member unhealthy. There is no cross-AZ coordinator
or route failover. An unavailable AZ may prevent replacement in that slot.

The implementation borrows membership, readiness and conservative uncertainty
handling from the ECS reference, but does not copy its two-slot constants or
large protected security/lifecycle framework. Existing ECS evidence does not
qualify this EKS code. Live private-subnet traffic, replacement timing and failure
recovery remain **UNVERIFIED** after local tests.

## Migration from partially retired state — plan only

1. Preserve current state versions, the original secret/ESO/OIDC/boundary/hosting
   retentions and the existing drift report outside Git. No state command or
   reconciliation is authorized by this document.
2. Obtain a separate scoped reconciliation review: native ASG/EC2/EIP membership,
   legacy `module.instance[AZ].aws_instance.nat`, `aws_eip_association.nat` and
   `aws_route.default` bindings may disagree after manual retirement. Do not use
   a blind apply, fake moved block, state removal or import to infer ownership.
3. Review plans with `nat_recovery_enabled=false`: no NAT compute/callback
   admission, but stable EIPs and retained controller resources can still cost.
   Stable SG/profile/EIP identities should be preserved where actually present.
   The source change alone does not reconcile remote state.
4. For each surviving legacy default route, separately prove the exact prior
   NAT ENI and slot ownership. Bind only those IDs through
   `approved_predecessor_enis` in the reviewed migration inputs. The default is
   empty; a blackhole to an unknown ENI is deliberately rejected. Never commit
   live inventory IDs as generic defaults or admit another slot's predecessor.
5. After state, IAM bytes and cost/ownership review, separately authorize enabling
   `nat_recovery_enabled=true`. The reviewed source maps it to all ASG capacity,
   controller concurrency, event-rule state and CONTROL admission. This is a
   future mutating action; no activation occurred during local development.
6. In that authorized window, observe all three numeric launch versions and
   resolved current members, bootstrap/readback receipts, then genuine traffic
   from each private subnet through the intended EIP. A same-AZ replacement drill
   must retain original failure records and test bounded recovery; no claim of
   AZ failover or ongoing forwarding health follows from it.

Before any future retirement/maintenance, inhibit CONTROL, event delivery and
new ASG launches through separately reviewed authority, then settle outstanding
callbacks/journal attempts, native activities and members. Concurrency zero,
desired zero and an empty queue alone do not prove quiescence. Retain the journal
and failure evidence until the owner decides their retention. Current retirement uses the manual lab-cleanup guide; historical executor plans are not reused.

The former executor construction-guard tests are archived. Active NAT configuration/recovery tests remain part of platform CI. Use [lab cleanup](lab-cleanup.md#3-nat-ha-and-exact-residuals) for retirement: protected journal/failure resources need an explicit final disposition; none is implicitly disposable.

## Resources and cost model before any AWS drill

Three ASGs and three launch templates replace three directly managed EC2s.
Steady compute remains three `t3.micro`, three EIPs and three 8 GiB gp3 roots;
ASG has no separate service fee. Shared additions: one Lambda/role/inline policy,
log group (7 days), on-demand DynamoDB table + CONTROL item, SQS queue + policy,
EventBridge rule/target, Lambda invocation permission/async destination and two
alarms. No new paid CMK or always-running forwarding probe is added.

Using the already recorded us-east-1 rates (not an invoice or new quote), NAT
baseline is 3 x $0.0104/h compute + 3 x $0.005/h IPv4 + 24 x $0.08/GB-month
storage: about **$1.17/day**, or **$0.39 for 8 hours**, excluding transfer/CPU
throttling/other platform resources. Standard credits prevent surplus-credit
charges; they do not guarantee forwarding capacity. Allow brief extra public IP
usage during bootstrap before the stable EIP replaces the ephemeral address.

At standard first-tier rates without free allowances, 100 callbacks at the full
180s/128MiB ceiling are about $0.038 in Lambda duration. Two standard alarms add
about $0.20/month (~$0.007/day); DynamoDB reads/writes, tiny journal storage, SQS,
logs and transfer are usage-based and not a hard cap. A provisional **$1 allowance
for recovery control plus $0.39 NAT baseline** covers a small 8h NAT-only drill,
not EKS/RDS/nodes/ALB, backups, taxes or extended retention. Reprice and count exact
resources before admission. If retirement is unavailable, costs continue beyond
the window; no agent deletion or automatic monetary stop is promised.

Pricing references: [EC2](https://aws.amazon.com/ec2/pricing/on-demand/),
[IPv4](https://aws.amazon.com/vpc/pricing/), [EBS](https://aws.amazon.com/ebs/pricing/),
[Lambda](https://aws.amazon.com/lambda/pricing/),
[CloudWatch](https://aws.amazon.com/cloudwatch/pricing/),
[DynamoDB](https://aws.amazon.com/dynamodb/pricing/on-demand/).

## Local verification

```text
python -B -m unittest discover -s scripts/validation -p "test_nat*.py"
python -B scripts/validation/package_nat_recovery.py --check
```

The ZIP is generated only from `recovery.py` by the deterministic local packager;
legacy A/B handler ZIPs are never packaged. Tests use SDK-shaped doubles for
three slots, stale/duplicate/foreign events, readiness, conditional concurrency,
generation inhibition, partial effects, ACK loss and safe refusal of uncertainty.
Parsed HCL tests reject capacity/IAM/ownership regressions. Terraform schema
validation uses a disposable copy, backend disabled, readonly locks and the
cached AWS 5.100.0 provider. No plan, apply, AWS call, Git or installation is part
of these checks. Future GitHub CI/build evidence remains a separate task.
