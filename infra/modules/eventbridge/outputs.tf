output "event_bus_name" {
  description = "Name of the custom EventBridge event bus."
  value       = aws_cloudwatch_event_bus.this.name
}

output "event_bus_arn" {
  description = "ARN of the custom EventBridge event bus."
  value       = aws_cloudwatch_event_bus.this.arn
}

output "rule_arns" {
  description = "ARNs of the EventBridge rules."
  value       = { for name, rule in aws_cloudwatch_event_rule.this : name => rule.arn }
}
