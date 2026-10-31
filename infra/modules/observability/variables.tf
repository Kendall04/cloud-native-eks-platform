variable "project_name" { type = string }
variable "environment" { type = string }
variable "region" { type = string }
variable "cluster_name" { type = string }
variable "oidc_provider_arn" { type = string }
variable "oidc_provider_url" { type = string }
variable "api_id" { type = string }
variable "db_instance_id" { type = string }
variable "queue_names" {
  type = object({ shipment = string, consumer_dlq = string, delivery_dlq = string })
}
variable "addon_version" {
  type    = string
  default = "v6.2.0-eksbuild.1"
  validation {
    condition     = var.addon_version == "v6.2.0-eksbuild.1"
    error_message = "Addon version changes require a reviewed configuration/compatibility check."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
variable "permissions_boundary" {
  description = "Permissions boundary for the telemetry workload identity."
  type        = string
  default     = null
}
