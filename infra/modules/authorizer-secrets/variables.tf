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

variable "secrets" {
  description = "Secrets Manager secret containers to create. This module never manages secret values."
  type = map(object({
    name                    = string
    description             = string
    recovery_window_in_days = optional(number, 7)
    kms_key_id              = optional(string, null)
  }))
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}
