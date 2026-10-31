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

variable "name" {
  description = "API Gateway name. Defaults to a derived project/environment name."
  type        = string
  default     = null
  nullable    = true
}

variable "description" {
  description = "Description for the API."
  type        = string
  default     = null
  nullable    = true
}

variable "protocol_type" {
  description = "API Gateway protocol type."
  type        = string
  default     = "HTTP"

  validation {
    condition     = var.protocol_type == "HTTP"
    error_message = "This module currently supports only HTTP APIs."
  }
}

variable "stage_name" {
  description = "Stage name for the API."
  type        = string
  default     = "$default"
}

variable "auto_deploy" {
  description = "Whether stage changes are deployed automatically."
  type        = bool
  default     = true
}

variable "access_log_retention_in_days" {
  description = "Retention period for API access logs."
  type        = number
  default     = 30
}

variable "cors_configuration" {
  description = "Optional CORS configuration for HTTP APIs."
  type = object({
    allow_origins     = list(string)
    allow_methods     = optional(list(string), ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    allow_headers     = optional(list(string), ["authorization", "content-type"])
    expose_headers    = optional(list(string), [])
    allow_credentials = optional(bool, false)
    max_age           = optional(number, 0)
  })
  default = {
    allow_origins = ["*"]
  }
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}

variable "vpc_id" {
  description = "VPC ID used by the API Gateway VPC link."
  type        = string
}

variable "vpc_link_subnet_ids" {
  description = "Private subnet IDs used by the API Gateway VPC link."
  type        = list(string)

  validation {
    condition     = length(var.vpc_link_subnet_ids) >= 2
    error_message = "vpc_link_subnet_ids must include at least two subnets."
  }
}


variable "jwt_authorizer_function_name" {
  description = "Lambda function name used by the request authorizer."
  type        = string
}

variable "jwt_authorizer_lambda_invoke_arn" {
  description = "Invoke ARN of the Lambda request authorizer."
  type        = string
}

variable "jwt_authorizer_identity_sources" {
  description = "Identity sources passed to the Lambda request authorizer."
  type        = list(string)
  default     = ["$request.header.Authorization"]
}

variable "jwt_authorizer_result_ttl_in_seconds" {
  description = "Authorizer cache TTL in seconds."
  type        = number
  default     = 0
}
