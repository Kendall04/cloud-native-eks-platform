include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config   = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name = local.env_config.locals.project_name
  environment  = local.env_config.locals.environment
  nat_mode     = regex("^gateway$|^instance$", local.env_config.locals.nat_mode)
}

terraform {
  source = "../../../modules/vpc"
}

inputs = {
  name                              = "${local.project_name}-${local.environment}-vpc"
  cidr_block                        = "10.0.0.0/16"
  availability_zones                = ["us-east-1a", "us-east-1b", "us-east-1c"]
  public_subnet_cidrs               = ["10.0.0.0/20", "10.0.16.0/20", "10.0.32.0/20"]
  private_subnet_cidrs              = ["10.0.128.0/20", "10.0.144.0/20", "10.0.160.0/20"]
  enable_nat_gateway                = local.nat_mode == "gateway"
  single_nat_gateway                = true
  manage_private_nat_gateway_routes = false
  eks_cluster_name                  = local.env_config.locals.eks_cluster_name
}
