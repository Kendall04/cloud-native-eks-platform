variable "name" { type = string }
variable "iam_permissions_boundary_arn" {
  description = "Operator-owned boundary limiting publisher and orchestrator to project application delivery; the executor cannot modify it."
  type        = string
}
variable "region" { type = string }
variable "artifact_bucket_name" { type = string }
variable "management_instance_id" { type = string }
variable "management_role_name" { type = string }
variable "repository_arns" { type = list(string) }
variable "tags" {
  type    = map(string)
  default = {}
}
variable "github_repository" {
  type    = string
  default = "Kendall04/cloud-native-eks-platform"
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use an exact owner/repository, never a wildcard."
  }
}
variable "github_oidc_provider_arn" {
  description = "Import/reuse the account provider when it already exists. Null creates it."
  type        = string
  default     = null
}

variable "project_name" {
  type    = string
  default = ""
}

variable "environment" {
  type    = string
  default = ""
}
