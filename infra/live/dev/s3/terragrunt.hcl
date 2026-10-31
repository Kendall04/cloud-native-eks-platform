include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config   = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name = local.env_config.locals.project_name
  environment  = local.env_config.locals.environment
  region       = local.env_config.locals.region
  account_id   = get_aws_account_id()
}

terraform {
  source = "../../../modules/s3"
}

inputs = {
  buckets = {
    artifacts = {
      bucket_name        = "${local.project_name}-${local.account_id}-${local.environment}-${local.region}-artifacts"
      versioning_enabled = true
      force_destroy      = false
      encryption_type    = "AES256"
    }
    logs = {
      bucket_name        = "${local.project_name}-${local.account_id}-${local.environment}-${local.region}-logs"
      versioning_enabled = true
      force_destroy      = false
      encryption_type    = "AES256"
    }
  }
}
