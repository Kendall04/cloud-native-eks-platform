output "repository_arns" {
  description = "ARNs of the created ECR repositories."
  value       = { for name, repository in aws_ecr_repository.this : name => repository.arn }
}

output "repository_names" {
  description = "Names of the created ECR repositories."
  value       = keys(aws_ecr_repository.this)
}

output "repository_urls" {
  description = "Repository URLs for the created ECR repositories."
  value       = { for name, repository in aws_ecr_repository.this : name => repository.repository_url }
}

