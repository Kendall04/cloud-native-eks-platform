locals {
  names = toset(["auth-runtime-db", "auth-migration-db", "shipment-runtime-db", "shipment-migration-db", "tracking-runtime-db", "tracking-migration-db", "internal-trust", "bootstrap-admin"])
  oidc  = replace(var.oidc_provider_url, "https://", "")
}
resource "aws_secretsmanager_secret" "runtime" {
  for_each                = local.names
  name                    = "${var.project_name}/${var.environment}/runtime/${each.key}"
  recovery_window_in_days = 30
  tags                    = merge(var.tags, { Project = var.project_name, Environment = var.environment })
}
resource "aws_iam_role" "eso" {
  name                 = "${var.project_name}-${var.environment}-external-secrets"
  permissions_boundary = var.permissions_boundary
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = var.oidc_provider_arn }
      Condition = { StringEquals = {
        "${local.oidc}:sub" = "system:serviceaccount:kube-system:external-secrets"
        "${local.oidc}:aud" = "sts.amazonaws.com"
      } }
    }]
  })
  tags = var.tags
}
resource "aws_iam_role_policy" "eso_read" {
  role = aws_iam_role.eso.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = concat([for secret in aws_secretsmanager_secret.runtime : secret.arn], values(var.shared_secret_arns))
    }]
  })
}
