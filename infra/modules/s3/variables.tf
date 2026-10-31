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

variable "buckets" {
  description = "Map of S3 buckets keyed by a logical identifier."
  type = map(object({
    bucket_name        = string
    force_destroy      = optional(bool, false)
    versioning_enabled = optional(bool, true)
    encryption_type    = optional(string, "AES256")
    kms_master_key_id  = optional(string, null)
  }))
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}

