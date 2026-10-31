output "queue_arns" {
  description = "ARNs of the primary queues."
  value       = { for name, queue in aws_sqs_queue.this : name => queue.arn }
}

output "queue_urls" {
  description = "URLs of the primary queues."
  value       = { for name, queue in aws_sqs_queue.this : name => queue.url }
}

output "dlq_arns" {
  description = "ARNs of the dead-letter queues."
  value       = { for name, queue in aws_sqs_queue.dlq : name => queue.arn }
}

output "dlq_urls" {
  description = "URLs of the dead-letter queues."
  value       = { for name, queue in aws_sqs_queue.dlq : name => queue.url }
}
