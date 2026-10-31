# Private operator access

[Deployment](deployment.md) · [Secrets/database](secrets-database.md) · [Lab cleanup](lab-cleanup.md)

Management is a private EC2 host registered with SSM. It has no inbound SSH path. Its instance identity runs apps-scoped CD; an operator's temporary identity performs platform bootstrap through a separate authorized network session. Forwarding traffic does not grant Kubernetes/database privileges.

## EKS from Windows

For the proposed certification, prefer the existing validated loopback route: SSM remote-host forwarding from the exact management instance to the real EKS endpoint/443, listening only on local 18443. Use a private run-specific kubeconfig with server `https://127.0.0.1:18443`, `tls-server-name` equal to the actual EKS hostname and unchanged real CA; never disable verification or set a proxy URL. Bootstrap accepts this form; use [lab cleanup](lab-cleanup.md) for current retirement prerequisites. It requires no Windows hosts/security edit. The exact-hostname method below is an administrative alternative, not an implicit extra permission for this cycle.

Use AWS CLI v2, Session Manager plugin and a principal permitted to start the remote-host forwarding document on the exact management instance. Obtain the current EKS endpoint FQDN, certificate authority and management ID from reviewed outputs/DescribeCluster.

```powershell
aws --profile <operator-profile> --region us-east-1 ssm start-session --target <management-instance-id> --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters 'host=[<real-eks-fqdn>],portNumber=[443],localPortNumber=[443]'
```

In a separate terminal, confirm the listener binds loopback only. Preserve existing Windows hosts entries; temporarily map only the real EKS FQDN to `127.0.0.1` with local administrator authorization, then flush DNS. Bypass proxies only for that FQDN. Keep kubeconfig's server equal to the real `https://<eks-fqdn>` and preserve its real CA, so TLS hostname validation/SNI remains correct. Never disable certificate verification.

AWS credentials stay in the local operator process; management forwards encrypted traffic. The operator's identity generates EKS tokens. Management's deployer role does not become a cluster administrator. After operations, stop forwarding, remove only the hosts entry added for this run and restore proxy/environment settings. Do not leave mappings tied to a retired cluster generation.

## RDS from Windows

```powershell
aws --profile <operator-profile> --region us-east-1 ssm start-session --target <management-instance-id> --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters 'host=[<real-rds-fqdn>],portNumber=[5432],localPortNumber=[15432]'
```

Confirm loopback-only TCP/15432. In the local bootstrap process set `PGHOSTADDR=127.0.0.1` and `PGPORT=15432`, restoring previous values afterwards. Keep the generated database host equal to the real RDS FQDN. Libpq routes via hostaddr while `sslmode=verify-full` verifies the real hostname using the committed RDS CA. Phase 2 calls `database.bootstrap(c)`; database.py is not a standalone CLI.

The existing bootstrap also supports the explicit run-local `RDS_LOCAL_FORWARD_PORT=15432`: it supplies loopback hostaddr/port while retaining the actual RDS host and VerifyFull CA. This is the proposed path; credentials remain in the local operator process and are never transferred to management or the Linux test VM.

The local operator reads the master secret into memory through Secrets Manager. Never persist it or transfer it to management. RDS ingress permits the EKS cluster SG and management SG. Management PostgreSQL egress is limited to the three reviewed private subnet CIDRs on 5432; that scope is subnet-wide rather than DB-exclusive.

## Preserve transit through cleanup

Management must survive any RDS retirement that needs its private path and the final Kubernetes observation. Before removing it, confirm frozen delivery, matching EKS generation, controller cleanup and no remaining Kubernetes work as required by [lab cleanup](lab-cleanup.md). The former executor checkpoint is historical; current cleanup records these checks manually.

Lost connectivity is not evidence of absence. If recovery needs Kubernetes after transit has closed, stop for reviewed recovery. Keep external journals and their independent head checkpoint; never delete one to bypass a mismatch.
