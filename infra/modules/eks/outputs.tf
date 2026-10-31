output "cluster_name" {
  description = "Name of the EKS cluster."
  value       = aws_eks_cluster.this.name
}

output "region" {
  description = "AWS region of the EKS cluster."
  value       = var.region
}

output "vpc_id" {
  description = "VPC ID where the EKS cluster runs."
  value       = var.vpc_id
}

output "cluster_endpoint" {
  description = "Private endpoint of the EKS cluster."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_security_group" {
  description = "Cluster security group ID created by Amazon EKS."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "node_group_names" {
  description = "Names of the managed node groups."
  value = sort(concat(
    [for group in aws_eks_node_group.encrypted : group.node_group_name],
  ))
}

output "oidc_provider_arn" {
  description = "ARN of the IAM OIDC provider used for service accounts."
  value       = aws_iam_openid_connect_provider.this.arn
}

output "oidc_provider_url" {
  description = "Issuer URL of the IAM OIDC provider used for service accounts."
  value       = aws_iam_openid_connect_provider.this.url
}

output "aws_load_balancer_controller_role_arn" {
  description = "IAM role ARN reserved for the AWS Load Balancer Controller service account."
  value       = try(aws_iam_role.aws_load_balancer_controller[0].arn, null)
}

output "aws_load_balancer_controller_namespace" {
  description = "Namespace expected for the AWS Load Balancer Controller service account."
  value       = var.aws_load_balancer_controller_namespace
}

output "aws_load_balancer_controller_service_account_name" {
  description = "Service account name expected for the AWS Load Balancer Controller."
  value       = var.aws_load_balancer_controller_service_account_name
}

output "cluster_autoscaler_role_arn" {
  description = "IAM role ARN reserved for the Cluster Autoscaler service account."
  value       = try(aws_iam_role.cluster_autoscaler[0].arn, null)
}

output "cluster_autoscaler_namespace" {
  description = "Namespace expected for the Cluster Autoscaler service account."
  value       = var.cluster_autoscaler_namespace
}

output "cluster_autoscaler_service_account_name" {
  description = "Service account name expected for Cluster Autoscaler."
  value       = var.cluster_autoscaler_service_account_name
}
