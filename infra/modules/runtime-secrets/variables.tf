variable "project_name" { type = string }
variable "environment" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
variable "oidc_provider_arn" { type = string }
variable "oidc_provider_url" { type = string }
variable "shared_secret_arns" { type = map(string) }
variable "permissions_boundary" {
  description = "Permissions boundary for the external-secrets workload identity."
  type        = string
  default     = null
}

variable "region" {
  type    = string
  default = ""
}
