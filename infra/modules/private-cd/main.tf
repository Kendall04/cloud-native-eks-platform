data "aws_caller_identity" "current" {}

locals {
  bucket = "arn:aws:s3:::${var.artifact_bucket_name}"
  subjects = {
    publisher = ["repo:${var.github_repository}:ref:refs/heads/main", "repo:${var.github_repository}:ref:refs/heads/develop"]
    deployer  = ["repo:${var.github_repository}:environment:dev"]
  }
  provider_arn = var.github_oidc_provider_arn != null ? var.github_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
  inputs = {
    ArtifactKey = "^deploy-artifacts/dev/[0-9a-f]{40}/[0-9a-f]{64}\\.tar\\.gz$"
    # SSM's RE2 engine caps a single counted repetition at 1000. The two
    # adjacent ranges preserve the executor's exact 1..1024 character contract.
    ArtifactVersionId        = "^[A-Za-z0-9._~+/-]{1,1000}[A-Za-z0-9._~+/-]{0,24}$"
    ArtifactSha256           = "^[0-9a-f]{64}$"
    DeploymentId             = "^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$"
    ExpectedPreviousRevision = "^(0|[1-9][0-9]{0,8})$"
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.github_oidc_provider_arn == null ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS uses its trusted CA store for GitHub; no copied thumbprint.
  tags = var.tags
}

resource "aws_iam_role" "federated" {
  for_each             = local.subjects
  name                 = "${var.name}-${each.key == "publisher" ? "artifact-publisher" : "deployment-orchestrator-dev"}"
  permissions_boundary = var.iam_permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = local.provider_arn }
      Condition = { StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = each.value
      } }
    }]
  })
  max_session_duration = each.key == "deployer" ? 7200 : 3600
  tags                 = var.tags
}

resource "aws_iam_role_policy" "publisher" {
  role = aws_iam_role.federated["publisher"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages", "ecr:DescribeImageScanFindings"], Resource = var.repository_arns },
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = ["${local.bucket}/deploy-artifacts/dev/*", "${local.bucket}/image-records/dev/*"], Condition = { StringEquals = { "s3:if-none-match" = "*" } } },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = ["${local.bucket}/deploy-artifacts/dev/*", "${local.bucket}/image-records/dev/*", "${local.bucket}/environment-contracts/dev/*"] }
    ]
  })
}

resource "aws_ssm_document" "deploy" {
  name            = "${var.name}-deploy-apps"
  document_type   = "Command"
  document_format = "JSON"
  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Fixed platform deployer 1.0.0; application artifacts cannot supply commands."
    parameters = { for name, pattern in local.inputs : name => {
      type = "String", interpolationType = "ENV_VAR", allowedPattern = pattern
    } }
    mainSteps = [{
      action       = "aws:runShellScript", name = "DeployApprovedArtifact"
      precondition = { StringEquals = ["platformType", "Linux"] }
      inputs = {
        timeoutSeconds = "3600"
        runCommand     = ["set -eu", "exec runuser -u platform-deploy -- /opt/platform-deployer/venv/bin/python -E -s /opt/platform-deployer/executor.py --ArtifactKey \"$SSM_ArtifactKey\" --ArtifactVersionId \"$SSM_ArtifactVersionId\" --ArtifactSha256 \"$SSM_ArtifactSha256\" --DeploymentId \"$SSM_DeploymentId\" --ExpectedPreviousRevision \"$SSM_ExpectedPreviousRevision\""]
      }
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "orchestrator" {
  role = aws_iam_role.federated["deployer"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = ["${local.bucket}/deploy-artifacts/dev/*", "${local.bucket}/deployment-receipts/dev/*"] },
      { Effect = "Allow", Action = ["ssm:SendCommand"], Resource = [aws_ssm_document.deploy.arn, "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/${var.management_instance_id}"] },
      # These APIs do not support resource-level permissions. No cancel/update document/session API.
      { Effect = "Allow", Action = ["ssm:GetCommandInvocation"], Resource = "*" }
    ]
  })
}

resource "aws_iam_role_policy" "management_artifacts" {
  role = var.management_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObjectVersion"], Resource = "${local.bucket}/deploy-artifacts/dev/*" },
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = local.bucket, Condition = { StringLike = { "s3:prefix" = ["deployment-receipts/dev/*"] } } },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${local.bucket}/deployment-receipts/dev/*" }
    ]
  })
}
