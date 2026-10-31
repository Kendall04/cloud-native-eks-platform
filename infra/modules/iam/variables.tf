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

variable "roles" {
  description = "Map of IAM roles keyed by role name."
  type = map(object({
    description          = optional(string, null)
    assume_role_policy   = string
    managed_policy_arns  = optional(list(string), [])
    inline_policies      = optional(map(string), {})
    max_session_duration = optional(number, 3600)
    path                 = optional(string, "/")
    permissions_boundary = optional(string, null)
    tags                 = optional(map(string), {})
  }))
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}

