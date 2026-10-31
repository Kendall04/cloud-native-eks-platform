variable "project_name" {
  description = "Project name used for tagging."
  type        = string
}

variable "iam_permissions_boundary_arn" {
  description = "Optional permissions boundary for the IAM roles created by this stack."
  type        = string
  default     = null
}

variable "environment" {
  description = "Environment name used for tagging."
  type        = string
}

variable "region" {
  description = "AWS region for the deployment."
  type        = string
}

variable "cluster_name" {
  description = "Name of the EKS cluster."
  type        = string
  default     = null
  nullable    = true
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster. Defaults to 1.35, the latest Amazon EKS standard-support version as of March 10, 2026."
  type        = string
  default     = "1.35"
}

variable "vpc_id" {
  description = "Existing VPC ID where the cluster and node groups are deployed."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs used by the control plane and managed node groups."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "private_subnet_ids must contain at least two private subnet IDs across different availability zones."
  }
}

variable "enabled_cluster_log_types" {
  description = "Control plane log types enabled for the cluster."
  type        = list(string)
  default     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
}

variable "cluster_log_retention_in_days" {
  description = "Retention period for the EKS control plane CloudWatch log group."
  type        = number
  default     = 30
}

variable "cluster_access_mode" {
  description = "EKS cluster authentication mode. API_AND_CONFIG_MAP enables access entries while keeping aws-auth compatibility."
  type        = string
  default     = "API_AND_CONFIG_MAP"

  validation {
    condition     = contains(["API", "API_AND_CONFIG_MAP", "CONFIG_MAP"], var.cluster_access_mode)
    error_message = "cluster_access_mode must be one of API, API_AND_CONFIG_MAP, or CONFIG_MAP."
  }
}

variable "bootstrap_cluster_creator_admin_permissions" {
  description = "Whether the cluster creator IAM principal is granted initial EKS cluster admin permissions."
  type        = bool
  default     = true
}

variable "create_aws_load_balancer_controller_prerequisites" {
  description = "Whether to create the IAM/IRSA prerequisites required by the AWS Load Balancer Controller."
  type        = bool
  default     = true
}

variable "aws_load_balancer_controller_namespace" {
  description = "Kubernetes namespace expected for the AWS Load Balancer Controller service account."
  type        = string
  default     = "kube-system"
}

variable "aws_load_balancer_controller_service_account_name" {
  description = "Kubernetes service account name expected for the AWS Load Balancer Controller."
  type        = string
  default     = "aws-load-balancer-controller"
}

variable "create_cluster_autoscaler_prerequisites" {
  description = "Whether to create the IAM/IRSA prerequisites required by Cluster Autoscaler."
  type        = bool
  default     = true
}

variable "cluster_autoscaler_namespace" {
  description = "Kubernetes namespace expected for the Cluster Autoscaler service account."
  type        = string
  default     = "kube-system"
}

variable "cluster_autoscaler_service_account_name" {
  description = "Kubernetes service account name expected for Cluster Autoscaler."
  type        = string
  default     = "cluster-autoscaler"
}

variable "api_node_group" {
  description = "Configuration for the API workload managed node group."
  type = object({
    instance_types = list(string)
    capacity_type  = string
    min_size       = number
    max_size       = number
    desired_size   = number
    disk_size      = optional(number, 50)
    ami_type       = optional(string, "AL2023_x86_64_STANDARD")
    labels         = optional(map(string), {})
    tags           = optional(map(string), {})
  })

  default = {
    instance_types = ["t3.large"]
    capacity_type  = "ON_DEMAND"
    min_size       = 2
    max_size       = 6
    desired_size   = 2
    disk_size      = 50
    ami_type       = "AL2023_x86_64_STANDARD"
    labels = {
      workload = "api"
    }
    tags = {
      workload = "api"
    }
  }

  validation {
    condition     = var.api_node_group.min_size <= var.api_node_group.desired_size && var.api_node_group.desired_size <= var.api_node_group.max_size
    error_message = "api_node_group desired_size must be between min_size and max_size."
  }
}

variable "worker_node_group" {
  description = "Configuration for the worker workload managed node group."
  type = object({
    instance_types = list(string)
    capacity_type  = string
    min_size       = number
    max_size       = number
    desired_size   = number
    disk_size      = optional(number, 50)
    ami_type       = optional(string, "AL2023_x86_64_STANDARD")
    labels         = optional(map(string), {})
    tags           = optional(map(string), {})
  })

  default = {
    instance_types = ["t3.large"]
    capacity_type  = "SPOT"
    min_size       = 1
    max_size       = 10
    desired_size   = 1
    disk_size      = 50
    ami_type       = "AL2023_x86_64_STANDARD"
    labels = {
      workload = "worker"
    }
    tags = {
      workload = "worker"
    }
  }

  validation {
    condition     = var.worker_node_group.min_size <= var.worker_node_group.desired_size && var.worker_node_group.desired_size <= var.worker_node_group.max_size
    error_message = "worker_node_group desired_size must be between min_size and max_size."
  }
}

variable "enabled_addons" {
  description = "AWS managed EKS addons to install."
  type        = list(string)
  default     = ["vpc-cni", "kube-proxy", "coredns", "aws-ebs-csi-driver"]

  validation {
    condition = length(setsubtract(
      toset(["vpc-cni", "kube-proxy", "coredns", "aws-ebs-csi-driver"]),
      toset(var.enabled_addons)
    )) == 0
    error_message = "enabled_addons must include vpc-cni, kube-proxy, coredns, and aws-ebs-csi-driver."
  }
}

variable "addon_versions" {
  description = "Optional reviewed addon versions; avoids unrelated upgrades during node maintenance."
  type        = map(string)
  default     = {}
}

variable "node_ami_release_version" {
  description = "Optional reviewed EKS-managed optimized AMI release. No custom AMI or user data is supplied by the launch template."
  type        = string
  default     = null
}

variable "tags" {
  description = "Additional tags applied to created resources."
  type        = map(string)
  default     = {}
}
