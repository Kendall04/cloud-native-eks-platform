variable "project_name" {
  description = "Project name used for tagging."
  type        = string
}

variable "environment" {
  description = "Environment name used for tagging."
  type        = string
}

variable "region" {
  description = "AWS region for the deployment."
  type        = string
}

variable "queues" {
  description = "Map of SQS queues keyed by the desired queue name."
  type = map(object({
    fifo_queue                    = optional(bool, false)
    content_based_deduplication   = optional(bool, false)
    delay_seconds                 = optional(number, 0)
    max_message_size              = optional(number, 262144)
    message_retention_seconds     = optional(number, 345600)
    visibility_timeout_seconds    = optional(number, 30)
    receive_wait_time_seconds     = optional(number, 0)
    create_dlq                    = optional(bool, true)
    dlq_name                      = optional(string, null)
    dlq_message_retention_seconds = optional(number, 1209600)
    max_receive_count             = optional(number, 5)
  }))
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}

variable "event_kms_key_arn" {
  description = "Customer-managed KMS key shared by this environment's event queues."
  type        = string
  validation {
    condition     = can(regex("^arn:[^:]+:kms:[^:]+:[0-9]{12}:key/", var.event_kms_key_arn))
    error_message = "Supply the event-encryption key ARN, never alias/aws/sqs."
  }
}
