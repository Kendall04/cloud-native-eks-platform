variable "project_name" {
  description = "Project name used for tags and naming."
  type        = string
}

variable "iam_permissions_boundary_arn" {
  description = "Optional permissions boundary for the management instance role."
  type        = string
  default     = null
}

variable "environment" {
  description = "Environment name used for tags and naming."
  type        = string
}

variable "region" {
  description = "AWS region."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}

variable "name" {
  description = "Name prefix for the management host resources."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where the management host runs."
  type        = string
}

variable "vpc_cidr_block" {
  description = "VPC CIDR used for DNS egress to the VPC resolver."
  type        = string
}

variable "private_subnet_id" {
  description = "Private subnet ID where the management host runs."
  type        = string
}

variable "rds_subnet_cidrs" {
  description = "Reviewed dev RDS subnet reachability scope, supplied by the VPC stack."
  type        = set(string)
  validation {
    condition     = var.rds_subnet_cidrs == toset(["10.0.128.0/20", "10.0.144.0/20", "10.0.160.0/20"])
    error_message = "PostgreSQL transit is limited to the three reviewed dev RDS private subnets."
  }
}

variable "cluster_name" {
  description = "EKS cluster name."
  type        = string
}

variable "cluster_security_group_id" {
  description = "EKS cluster security group ID."
  type        = string
}

variable "alb_frontend_security_group_id" {
  description = "Platform-owned frontend SG from API Gateway core; ordinary releases cannot change it."
  type        = string
  validation {
    condition     = can(regex("^sg-[0-9a-f]{8}([0-9a-f]{9})?$", var.alb_frontend_security_group_id))
    error_message = "A platform ALB frontend security group ID is required."
  }
}

variable "internal_alb_http_egress_security_group_ids" {
  description = "Internal ALB security group IDs the management host may reach over HTTP for private smoke tests."
  type        = set(string)
  default     = []
}

variable "instance_type" {
  description = "EC2 instance type for the management host."
  type        = string
  default     = "t3.nano"
}

variable "kubectl_version" {
  description = "kubectl version installed by user data."
  type        = string
  default     = "v1.35.0"
  validation {
    condition     = var.kubectl_version == "v1.35.0"
    error_message = "R4 checksum contract requires kubectl v1.35.0."
  }
}

variable "helm_version" {
  description = "Helm version installed by user data."
  type        = string
  default     = "v4.2.2"
  validation {
    condition     = var.helm_version == "v4.2.2"
    error_message = "R4 executor/checksum contract requires Helm v4.2.2."
  }
}

variable "root_volume_size" {
  description = "Root volume size in GiB."
  type        = number
  default     = 8
}

variable "api_endpoint" {
  description = "Public API Gateway endpoint for credential-free post-deploy smoke checks."
  type        = string
  default     = ""
}

variable "artifact_bucket_name" {
  description = "Optional S3 bucket name containing management artifacts."
  type        = string
  default     = null
}

variable "artifact_prefix" {
  description = "Optional S3 prefix where the management host can read artifacts."
  type        = string
  default     = "cluster-addons/dev"
}
