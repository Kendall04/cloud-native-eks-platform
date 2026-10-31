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
  source = "../../../modules/apigateway-core"
}

dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    vpc_id          = "vpc-00000000000000000"
    private_subnets = ["subnet-00000000000000000", "subnet-11111111111111111", "subnet-22222222222222222"]
  }

  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "api_gateway_authorizer" {
  config_path = "../api-gateway-authorizer"

  mock_outputs = {
    function_name       = "${local.project_name}-${local.environment}-api-jwt-authorizer"
    function_invoke_arn = "arn:aws:lambda:us-east-1:123456789012:function:${local.project_name}-${local.environment}-api-jwt-authorizer:$LATEST"
  }

  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

inputs = {
  name                             = "${local.project_name}-${local.environment}-http-api"
  description                      = "Shared HTTP API for the ${local.project_name} ${local.environment} environment."
  stage_name                       = "$default"
  vpc_id                           = dependency.vpc.outputs.vpc_id
  vpc_link_subnet_ids              = dependency.vpc.outputs.private_subnets
  jwt_authorizer_function_name     = dependency.api_gateway_authorizer.outputs.function_name
  jwt_authorizer_lambda_invoke_arn = dependency.api_gateway_authorizer.outputs.function_invoke_arn

  cors_configuration = {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_headers = ["authorization", "content-type", "x-requested-with"]
    max_age       = 3600
  }
}
