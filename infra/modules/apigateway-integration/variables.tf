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

variable "enabled" {
  description = "Whether to enable ALB discovery, integrations, and route creation."
  type        = bool
  default     = true
}

variable "api_id" {
  description = "ID of the HTTP API created by apigateway-core."
  type        = string
}

variable "vpc_link_id" {
  description = "ID of the API Gateway VPC link created by apigateway-core."
  type        = string
}

variable "authorizer_id" {
  description = "ID of the API Gateway request authorizer created by apigateway-core."
  type        = string
}

variable "alb_discovery_tags" {
  description = "Tags used to discover the ALB created by the Kubernetes ingress."
  type        = map(string)
  validation {
    condition     = alltrue([for key in ["elbv2.k8s.aws/cluster", "ingress.k8s.aws/stack", "Project", "Environment"] : try(length(var.alb_discovery_tags[key]) > 0, false)])
    error_message = "Discovery requires cluster, ingress stack, Project and Environment tags."
  }
}

variable "vpc_id" { type = string }
variable "frontend_security_group_id" { type = string }

variable "alb_listener_port" {
  description = "Listener port on the ALB used by API Gateway."
  type        = number
  default     = 80
}

variable "public_route_keys" {
  description = "Route keys that are exposed without an authorizer."
  type        = list(string)
  default     = []
}

variable "protected_route_keys" {
  description = "Route keys that require the API Gateway Lambda authorizer."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}
