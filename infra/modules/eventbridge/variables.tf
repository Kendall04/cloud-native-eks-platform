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

variable "event_bus_name" {
  description = "Name of the custom EventBridge event bus."
  type        = string
}

variable "rules" {
  description = "Map of EventBridge rules keyed by logical rule name."
  type = map(object({
    description                  = optional(string, null)
    event_pattern                = string
    target_queue_arn             = string
    target_queue_url             = string
    delivery_dlq_arn             = string
    delivery_dlq_url             = string
    maximum_event_age_in_seconds = optional(number, 3600)
    maximum_retry_attempts       = optional(number, 10)
    input_path                   = optional(string, "$.detail")
  }))
  validation {
    condition     = alltrue([for rule in values(var.rules) : rule.maximum_event_age_in_seconds >= 60 && rule.maximum_event_age_in_seconds <= 86400 && rule.maximum_retry_attempts >= 0 && rule.maximum_retry_attempts <= 185 && rule.target_queue_arn != rule.delivery_dlq_arn])
    error_message = "EventBridge retry limits must be valid and delivery DLQ distinct from target queue."
  }
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}
