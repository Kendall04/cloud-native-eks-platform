# Human-started temporary Windows-to-Linux authentication

Historical preparation record from October 2026; its authorization window has expired. Personal filesystem and SSH labels below were replaced with explicit placeholders during the 3 November editorial review. They are not claims of a new execution, and the source identity guards were not changed.

Prepared only. **No session token has been generated or transferred during preparation.** This procedure resumes only the already approved EKS scope, account `341936017254`, profile `cnp-cert-dev`. It does not authorize ECS, another profile, a longer window or additional AWS resources. See [the execution checkpoint](current-profile-aws-validation.md).

## One human-started command

Kendall runs this in his normal Windows PowerShell terminal after inspecting the two source files:

```powershell
# From the reviewed repository root; this historical procedure is not authorization.
& '.\scripts\operations\Start-CnpEksTemporarySession.ps1'
```

Keep that terminal open until the authorized AWS runtime has been retired. No execution-policy bypass, administrator prompt, pasted access key or credential file copy is involved. The script outputs only verified account, caller ARN and credential expiration when ready.

The script checks the existing Windows profile resolves exactly to `arn:aws:iam::341936017254:user/cnp-cert-admin`. Read-only preparation found **no MFA device** for this user. The command therefore pauses with the IAM console URL, asking Kendall to register an authenticator-app **TOTP** MFA device personally in the correct account and press Enter. A passkey alone cannot supply this API's six-digit TokenCode. The script never registers a device or reads its seed/QR secret. It then asks for a fresh six-digit MFA code through hidden terminal input; the code is passed directly to the Windows SDK in memory, never as a command argument.

This MFA prerequisite is essential: [GetSessionToken without MFA cannot perform IAM operations](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetSessionToken.html), so it would not support the 17-stack reconstruction. The script refuses to issue a session unless exactly one registered MFA device is found. It does not fall back to permanent keys, another profile or a new role. Multiple devices require a deliberate source/procedure review rather than guessing one.

## Preparation before the token request

SSH uses the existing `<WINDOWS_SSH_CONFIG>`, BatchMode and StrictHostKeyChecking=yes; no host-key changes. The Linux source must match the clean Windows commit and script hash. The user-started command performs the following local/tool preparation **before** requesting a token:

- Install only source-pinned Terraform **1.13.4**, Terragrunt **0.93.3** and kubectl **1.35.0** into the EKS checkout's ignored private tools directory, verifying the exact SHA256 values recorded in source. No global installation is replaced. Reused binaries must match their verified receipt.
- Require existing Helm **4.2.2**, Session Manager plugin and at least 3 GiB free. Preparation discovered global Linux defaults Terraform 1.15.7, Terragrunt 1.0.8 and kubectl 1.36.2; those defaults must not silently become the execution toolchain.
- Run an isolated backend-free schema check with the pinned Terraform and AWS provider **5.100.0**, readonly approved lockfile, no AWS credentials and metadata access disabled. This tests the provider's local TLS in Linux before any real credentials cross the SSH connection. Checksums and TLS validation remain enabled. Failed preparation stops before token issuance.

No handoff mode or installer was executed by the agent during preparation. Unit tests use only synthetic in-memory strings, and the SDK resolution test makes no AWS service request.

## How the context remains usable

Windows obtains MFA-authenticated temporary credentials through the existing profile's SDK. Only that temporary response crosses verified encrypted SSH **stdin**, never the command line. Long-term Windows profile credentials remain on Windows. The remote controller holds the response in memory and exposes a same-UID Unix socket under a mode-0700 directory on `/run/user/<uid>` tmpfs. Core dumps are disabled for the controller.

The tmpfs AWS config contains only `[profile cnp-cert-dev]`, region and a [credential_process](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sourcing-external.html) command. It contains no key/token. The helper supplies versioned temporary-credential JSON only into the SDK's private pipe; it must never be invoked manually or logged. AWS CLI, boto3 and Terraform's AWS SDK can therefore select the same explicit profile across later processes. This corrects the limitation of a one-shot `ssh` environment that disappears when its command exits.

The controller first verifies remote STS and publishes an ignored **non-secret** ACTIVE marker with owner, config/socket paths and expiration. The agent then resumes via the following wrapper; no credentials appear in its arguments:

```text
ssh -F <WINDOWS_SSH_CONFIG> -o BatchMode=yes -o StrictHostKeyChecking=yes <REVIEWED_SSH_ALIAS> "cd <REVIEWED_LINUX_CHECKOUT> && python3 scripts/operations/cnp_eks_temporary_session.py run -- aws --profile cnp-cert-dev --region us-east-1 sts get-caller-identity"
```

Use the same `run --` wrapper for Terragrunt, Terraform and their child processes, Helm/kubectl and approved repository operation scripts. It removes inherited AWS credentials/profiles/endpoints and debug settings, selects only the ephemeral profile/config, disables metadata fallback and prepends the verified private binaries. It rejects other profile/region arguments, other working directories, shell snippets, Private CD and common raw credential/Secret-output commands. The children inherit this context; their SDKs resolve credential_process normally. The source's `--profile cnp-cert-dev` remains usable; no persistent `~/.aws` profile is installed.

This is credential transport and accidental-output protection, **not an IAM sandbox**. GetSessionToken preserves the source user's permissions, currently AdministratorAccess; the EKS scope still comes from the user's approval and the reviewed operation scope and [manual cleanup prerequisites](lab-cleanup.md). Processes under the same Linux UID or root are not isolated from one another's memory. Do not reuse this marker/socket/config for ECS or another repository. No shared cross-project broker is proposed.

## Duration, stop and cleanup

Allow at least **four hours remaining** to obtain a usable session, finish the finite validation and retire safely. The token is at most six hours and shortened to expire before the current conservative session end, **17 October 2026 04:33:05 UTC**. There is no automatic refresh, role chain or renewal. If the window is expired or insufficient, stop and coordinate a fresh execution window before requesting credentials. Acquiring credentials does not start the resource-based billing clock or extend the USD 8 envelope. Record the first billable resource and start retirement no later than four hours afterward, sooner if the remaining authentication/window requires it.

After runtime retirement, Kendall presses **Ctrl+C** in the Windows terminal. SSH stdin closure, disconnect or expiration also closes the lease. The controller stops only wrapper-registered child process groups whose PID/start-time/ownership still match, closes the socket, removes only its own tmpfs config/socket directory and marks the non-secret marker CLOSED. It does not kill unrelated Docker/SQL processes, delete evidence or run AWS teardown automatically. Stop active operations and complete the reviewed [lab cleanup](lab-cleanup.md) before closing authentication.

Closing the lease does not revoke STS credentials already cached in a process or remove AWS resources. Registered children are terminated, but AWS credentials themselves remain valid until their stated expiration. No cryptographic memory-erasure or protection against a compromised local administrator is claimed. No long-term credential is written to Linux, Git, transcript or logs.

## Windows TLS result

The existing Windows failure was reproduced with the official pinned Terraform binary, backend-free and credential-free, with local mTLS certificate rejection. No proxy was configured, and a loopback-only NO_PROXY test did not fix it. No supported minimal local correction has been established without changing security configuration or validation. This procedure does not disable plugin TLS, alter certificate stores or try random versions; it uses the exact approved Linux toolchain and verifies its provider schema before requesting credentials.

Source for review: [PowerShell launcher](../../scripts/operations/Start-CnpEksTemporarySession.ps1), [controller/wrapper](../../scripts/operations/cnp_eks_temporary_session.py), [offline tests](../../scripts/validation/test_cnp_eks_temporary_session.py). Actual MFA-authenticated STS issuance and end-to-end Terraform authorization remain unexecuted until Kendall starts this procedure.
