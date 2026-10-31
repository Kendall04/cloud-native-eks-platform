output "instance_id" {
  description = "Management host instance ID."
  value       = aws_instance.management.id
}

output "private_ip" {
  description = "Management host private IP."
  value       = aws_instance.management.private_ip
}

output "security_group_id" {
  description = "Management host security group ID."
  value       = aws_security_group.management.id
}

output "iam_role_arn" {
  description = "Management host IAM role ARN."
  value       = aws_iam_role.management.arn
}

output "iam_role_name" { value = aws_iam_role.management.name }

output "iam_instance_profile_name" {
  description = "Management host instance profile name."
  value       = aws_iam_instance_profile.management.name
}
