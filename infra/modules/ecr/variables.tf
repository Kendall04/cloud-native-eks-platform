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

variable "repositories" {
  description = "Map of ECR repositories keyed by repository name."
  type = map(object({
    image_tag_mutability = optional(string, "IMMUTABLE")
    scan_on_push         = optional(bool, true)
    force_delete         = optional(bool, false)
    encryption_type      = optional(string, "AES256")
    kms_key              = optional(string, null)
    lifecycle_policy     = optional(string, null)
  }))
}

variable "default_lifecycle_policy" {
  description = "Default lifecycle policy JSON applied to repositories that do not define their own lifecycle policy."
  type        = string
  default     = null
  nullable    = true
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}
