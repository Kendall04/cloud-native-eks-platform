include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config   = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  vpc_config   = read_terragrunt_config("${get_terragrunt_dir()}/../vpc/terragrunt.hcl")
  project_name = local.env_config.locals.project_name
  environment  = local.env_config.locals.environment
  nat_mode     = regex("^gateway$|^instance$", local.env_config.locals.nat_mode)
}

terraform {
  source = "../../../modules//nat-egress"
}

dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    vpc_id                  = "vpc-00000000000000000"
    availability_zones      = ["us-east-1a", "us-east-1b", "us-east-1c"]
    public_subnet_ids       = ["subnet-00000000000000000", "subnet-11111111111111111", "subnet-22222222222222222"]
    private_subnet_cidrs    = ["10.0.128.0/20", "10.0.144.0/20", "10.0.160.0/20"]
    private_route_table_ids = ["rtb-00000000000000000", "rtb-11111111111111111", "rtb-22222222222222222"]
    nat_gateway_ids         = ["nat-00000000000000000"]
  }

  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

inputs = {
  name_prefix               = "${local.project_name}-${local.environment}"
  nat_mode                  = local.nat_mode
  vpc_id                    = dependency.vpc.outputs.vpc_id
  availability_zones        = dependency.vpc.outputs.availability_zones
  public_subnet_ids         = dependency.vpc.outputs.public_subnet_ids
  private_subnet_cidrs      = local.vpc_config.inputs.private_subnet_cidrs
  private_route_table_ids   = dependency.vpc.outputs.private_route_table_ids
  nat_gateway_ids           = dependency.vpc.outputs.nat_gateway_ids
  instance_type             = local.env_config.locals.nat_instance_type
  ami_id                    = "ami-03c3da4cfa8e8943a"
  key_name                  = local.env_config.locals.nat_instance_key_name
  allowed_ssh_cidr          = local.env_config.locals.nat_instance_allowed_ssh_cidr
  enable_ssm                = local.env_config.locals.nat_instance_enable_ssm
  recovery_enabled          = local.env_config.locals.nat_recovery_enabled
  approved_predecessor_enis = {} # Exact migration inputs require a separate ownership review.
}
