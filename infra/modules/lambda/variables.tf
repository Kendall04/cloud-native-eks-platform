variable "project_name" {
  description = "Project name used for tagging."
  type        = string
}

variable "iam_permissions_boundary_arn" {
  description = "Optional permissions boundary for the function execution role."
  type        = string
  default     = null
}

variable "environment" {
  description = "Environment name used for tagging."
  type        = string
}

variable "region" {
  description = "AWS region for the deployment."
  type        = string
}

variable "function_name" {
  description = "Lambda function name."
  type        = string
}

variable "description" {
  description = "Lambda description."
  type        = string
  default     = null
  nullable    = true
}

variable "source_dir" {
  description = "Authorizer source root; only src/index.mjs is packaged. AWS SDK is supplied by nodejs22.x."
  type        = string
}

variable "handler" {
  description = "Lambda handler."
  type        = string
}

variable "runtime" {
  description = "Lambda runtime."
  type        = string
}

variable "timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 30
}

variable "memory_size" {
  description = "Lambda memory size in MiB."
  type        = number
  default     = 256
}

variable "architectures" {
  description = "Lambda instruction set architectures."
  type        = list(string)
  default     = ["arm64"]
}

variable "environment_variables" {
  description = "Environment variables for the Lambda function."
  type        = map(string)
  default     = {}
}

variable "managed_policy_arns" {
  description = "Managed IAM policies attached to the Lambda execution role."
  type        = list(string)
  default     = []
}

variable "inline_policy_json" {
  description = "Optional inline IAM policy JSON attached to the Lambda execution role."
  type        = string
  default     = null
  nullable    = true
}

variable "sqs_event_sources" {
  description = "SQS event source mappings keyed by logical name."
  type = map(object({
    event_source_arn                   = string
    batch_size                         = optional(number, 10)
    maximum_batching_window_in_seconds = optional(number, 0)
    enabled                            = optional(bool, true)
  }))
  default = {}
}

variable "log_retention_in_days" {
  description = "CloudWatch log retention for the Lambda function."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}
