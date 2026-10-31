output "secret_arns" {
  description = "ARNs of the authorizer Secrets Manager secret containers."
  value       = { for key, secret in aws_secretsmanager_secret.this : key => secret.arn }
}

output "secret_names" {
  description = "Names of the authorizer Secrets Manager secret containers."
  value       = { for key, secret in aws_secretsmanager_secret.this : key => secret.name }
}
