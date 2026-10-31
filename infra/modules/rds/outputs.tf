output "db_instance_arn" {
  description = "ARN of the DB instance."
  value       = aws_db_instance.this.arn
}

output "db_instance_endpoint" {
  description = "Connection endpoint for the DB instance."
  value       = aws_db_instance.this.endpoint
}

output "db_instance_address" {
  description = "DNS address for the DB instance."
  value       = aws_db_instance.this.address
}

output "db_instance_id" {
  description = "Identifier of the DB instance."
  value       = aws_db_instance.this.identifier
}

output "db_instance_port" {
  description = "Port of the DB instance."
  value       = aws_db_instance.this.port
}

output "security_group_id" {
  description = "Security group ID attached to the DB instance."
  value       = aws_security_group.this.id
}

output "subnet_group_name" {
  description = "Name of the DB subnet group."
  value       = aws_db_subnet_group.this.name
}

output "master_user_secret_arn" {
  description = "Secrets Manager ARN containing the managed master password, when enabled."
  value       = try(aws_db_instance.this.master_user_secret[0].secret_arn, null)
}

