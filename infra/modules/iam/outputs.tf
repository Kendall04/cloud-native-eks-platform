output "role_arns" {
  description = "ARNs of the created IAM roles."
  value       = { for name, role in aws_iam_role.this : name => role.arn }
}

output "role_names" {
  description = "Names of the created IAM roles."
  value       = keys(aws_iam_role.this)
}

