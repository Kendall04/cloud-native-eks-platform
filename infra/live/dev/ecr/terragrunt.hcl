include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config   = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name = local.env_config.locals.project_name
  environment  = local.env_config.locals.environment
  lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 14 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 14
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

terraform {
  source = "../../../modules/ecr"
}

inputs = {
  default_lifecycle_policy = local.lifecycle_policy

  repositories = {
    auth-service = {
      image_tag_mutability = "IMMUTABLE"
      scan_on_push         = true
    }
    shipment-service = {
      image_tag_mutability = "IMMUTABLE"
      scan_on_push         = true
    }
    tracking-service = {
      image_tag_mutability = "IMMUTABLE"
      scan_on_push         = true
    }
  }
}
