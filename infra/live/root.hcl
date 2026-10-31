terraform_version_constraint  = ">= 1.6.0"
terragrunt_version_constraint = ">= 0.55.0"

locals {
  env_config       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name     = local.env_config.locals.project_name
  environment      = local.env_config.locals.environment
  region           = local.env_config.locals.region
  aws_account_id   = get_aws_account_id()
  state_bucket     = "${local.project_name}-${local.aws_account_id}-${local.environment}-${local.region}-tfstate"
  state_lock_table = "${local.project_name}-${local.aws_account_id}-${local.environment}-terraform-locks"
  tags             = try(local.env_config.locals.tags, {})
}

remote_state {
  backend = "s3"

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }

  config = {
    bucket         = local.state_bucket
    key            = "${path_relative_to_include()}/terraform.tfstate"
    region         = local.region
    encrypt        = true
    dynamodb_table = local.state_lock_table

    s3_bucket_tags = merge(local.tags, {
      Name = local.state_bucket
    })

    dynamodb_table_tags = merge(local.tags, {
      Name = local.state_lock_table
    })

    skip_bucket_enforced_tls           = false
    skip_bucket_public_access_blocking = false
    skip_bucket_root_access            = false
    skip_bucket_versioning             = false
    enable_lock_table_ssencryption     = true
  }
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = var.region

  default_tags {
    tags = merge(var.tags, {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terragrunt"
    })
  }
}
EOF
}

inputs = {
  project_name = local.project_name
  environment  = local.environment
  region       = local.region
  tags         = local.tags
}
