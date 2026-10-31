output "nat_instance_ids" {
  description = "Deprecated: dynamic ASG members require native discovery; no fixed instance IDs."
  value       = {}
}

output "nat_instance_public_ips" {
  description = "NAT instance public IPs keyed by availability zone when nat_mode is instance."
  value       = { for az, instance in module.instance : az => instance.public_ip }
}

output "default_route_table_ids" {
  description = "Private route tables managed by this module."
  value       = var.private_route_table_ids
}

output "nat_asg_names" { value = { for az, group in aws_autoscaling_group.nat : az => group.name } }
output "nat_recovery_enabled" { value = var.recovery_enabled && var.nat_mode == "instance" }
output "nat_journal_table" { value = try(aws_dynamodb_table.recovery[0].name, null) }
output "nat_failure_queue_url" { value = try(aws_sqs_queue.failures[0].url, null) }
