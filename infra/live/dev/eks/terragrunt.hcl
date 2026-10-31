include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

dependencies {
  paths = ["../nat"]
}

locals {
  env_config = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

terraform {
  source = "../../../modules/eks"
}

dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    vpc_id          = "vpc-00000000000000000"
    private_subnets = ["subnet-00000000000000000", "subnet-11111111111111111", "subnet-22222222222222222"]
  }

  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

inputs = {
  api_node_group = {
    instance_types = ["t3.large"]
    capacity_type  = "ON_DEMAND"
    min_size       = 2
    max_size       = 2
    desired_size   = 2
    disk_size      = 50
    ami_type       = "AL2023_x86_64_STANDARD"
    labels         = { workload = "api" }
    tags           = { workload = "api" }
  }
  worker_node_group = {
    instance_types = ["t3.large"]
    capacity_type  = "SPOT"
    min_size       = 1
    max_size       = 2
    desired_size   = 1
    disk_size      = 50
    ami_type       = "AL2023_x86_64_STANDARD"
    labels         = { workload = "worker" }
    tags           = { workload = "worker" }
  }
  node_ami_release_version = "1.35.8-20261003"
  addon_versions = {
    vpc-cni            = "v1.23.2-eksbuild.1"
    coredns            = "v1.14.7-eksbuild.11"
    kube-proxy         = "v1.35.3-eksbuild.49"
    aws-ebs-csi-driver = "v1.66.0-eksbuild.1"
  }
  iam_permissions_boundary_arn                      = "arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-eks-workload-boundary"
  cluster_name                                      = local.env_config.locals.eks_cluster_name
  vpc_id                                            = dependency.vpc.outputs.vpc_id
  private_subnet_ids                                = dependency.vpc.outputs.private_subnets
  create_aws_load_balancer_controller_prerequisites = true
  create_cluster_autoscaler_prerequisites           = true
}
