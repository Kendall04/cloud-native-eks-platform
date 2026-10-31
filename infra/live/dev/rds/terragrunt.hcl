include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config   = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name = local.env_config.locals.project_name
  environment  = local.env_config.locals.environment
}

terraform {
  source = "../../../modules/rds"
}

dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    vpc_id             = "vpc-00000000000000000"
    vpc_cidr_block     = "10.20.0.0/16"
    private_subnet_ids = ["subnet-00000000000000000", "subnet-11111111111111111"]
  }

  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

inputs = {
  name                      = "${local.project_name}-${local.environment}-postgres"
  engine                    = "postgres"
  engine_version            = "15.18"
  instance_class            = "db.t4g.micro"
  allocated_storage         = 20
  max_allocated_storage     = 100
  database_name             = local.env_config.locals.platform_database_name
  username                  = "platform_admin"
  backup_retention_period   = 7
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.project_name}-${local.environment}-postgres-final"
  vpc_id                    = dependency.vpc.outputs.vpc_id
  subnet_ids                = dependency.vpc.outputs.private_subnet_ids
  allowed_cidr_blocks       = []
  # Retained, stopped database: restore current EKS/management SG access on rebuild.
  allowed_security_group_ids      = []
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
}
