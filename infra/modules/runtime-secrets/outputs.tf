output "secret_arns" { value = merge({ for k, v in aws_secretsmanager_secret.runtime : k => v.arn }, var.shared_secret_arns) }
output "eso_role_arn" { value = aws_iam_role.eso.arn }
