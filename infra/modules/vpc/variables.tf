variable "project_name" {
  description = "Project name used for tagging and naming."
  type        = string
}

variable "environment" {
  description = "Environment name used for tagging and naming."
  type        = string
}

variable "region" {
  description = "AWS region for the deployment."
  type        = string
}

variable "name" {
  description = "Explicit VPC name. Defaults to a derived project/environment name."
  type        = string
  default     = null
  nullable    = true
}

variable "cidr_block" {
  description = "Primary CIDR block for the VPC."
  type        = string
}

variable "availability_zones" {
  description = "Availability zones used for the public and private subnets."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 3
    error_message = "availability_zones must contain exactly 3 availability zones."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDR ranges for public subnets. Must align with availability_zones."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) == 3 && length(var.public_subnet_cidrs) == length(var.availability_zones)
    error_message = "public_subnet_cidrs must contain exactly 3 CIDR blocks and align with availability_zones."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR ranges for private subnets. Must align with availability_zones."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_cidrs) == 3 && length(var.private_subnet_cidrs) == length(var.availability_zones)
    error_message = "private_subnet_cidrs must contain exactly 3 CIDR blocks and align with availability_zones."
  }
}

variable "enable_dns_support" {
  description = "Whether the VPC should enable DNS support."
  type        = bool
  default     = true
}

variable "enable_dns_hostnames" {
  description = "Whether the VPC should enable DNS hostnames."
  type        = bool
  default     = true
}

variable "enable_nat_gateway" {
  description = "Whether to provision NAT gateways for private subnet egress."
  type        = bool
  default     = true
}

variable "single_nat_gateway" {
  description = "Whether to create a single shared NAT gateway instead of one per AZ."
  type        = bool
  default     = true
}

variable "manage_private_nat_gateway_routes" {
  description = "Whether this module should create default routes from private route tables to NAT gateways."
  type        = bool
  default     = true
}

variable "map_public_ip_on_launch" {
  description = "Whether instances launched in public subnets receive public IPs by default."
  type        = bool
  default     = false
}

variable "eks_cluster_name" {
  description = "Optional EKS cluster name used for subnet discovery tags."
  type        = string
  default     = null
  nullable    = true
}

variable "enable_eks_subnet_tags" {
  description = "Whether to apply EKS-oriented subnet tags for public and internal load balancers."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}
