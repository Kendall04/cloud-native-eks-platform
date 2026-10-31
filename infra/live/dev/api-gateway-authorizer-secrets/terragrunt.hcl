include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config   = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name = local.env_config.locals.project_name
  environment  = local.env_config.locals.environment

  auth_service_jwt_secret_id       = "${local.project_name}/${local.environment}/api-gateway-authorizer/auth-service-jwt-secret"
  platform_trusted_proxy_secret_id = "${local.project_name}/${local.environment}/api-gateway-authorizer/platform-trusted-proxy-secret"
}

terraform {
  source = "../../../modules/authorizer-secrets"
}

inputs = {
  secrets = {
    auth-service-jwt-secret = {
      name                    = local.auth_service_jwt_secret_id
      description             = "JWT signing secret reference for the API Gateway authorizer. Value is populated outside Terraform."
      recovery_window_in_days = 7
    }
    platform-trusted-proxy-secret = {
      name                    = local.platform_trusted_proxy_secret_id
      description             = "Trusted proxy header secret reference for the API Gateway authorizer. Value is populated outside Terraform."
      recovery_window_in_days = 7
    }
  }
}
