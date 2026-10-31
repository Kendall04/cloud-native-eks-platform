include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config        = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name      = local.env_config.locals.project_name
  environment       = local.env_config.locals.environment
  region            = local.env_config.locals.region
  lambda_source_dir = abspath("${get_terragrunt_dir()}/../../../../lambdas/api-gateway-jwt-authorizer")

}

terraform {
  source = "../../../modules/lambda"
}

dependency "authorizer_secrets" {
  config_path = "../api-gateway-authorizer-secrets"
  mock_outputs = {
    secret_names = {
      auth-service-jwt-secret       = "test/auth-jwt"
      platform-trusted-proxy-secret = "test/proxy"
    }
    secret_arns = {
      auth-service-jwt-secret       = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test/auth-jwt-EXAMPLE"
      platform-trusted-proxy-secret = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test/proxy-EXAMPLE"
    }
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

inputs = {
  iam_permissions_boundary_arn = "arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-management-workload-boundary"
  function_name                = "${local.project_name}-${local.environment}-api-jwt-authorizer"
  description                  = "JWT request authorizer for the shared HTTP API."
  source_dir                   = local.lambda_source_dir
  handler                      = "src/index.handler"
  runtime                      = "nodejs22.x"
  timeout                      = 10
  memory_size                  = 128

  environment_variables = {
    JWT_ISSUER                       = local.env_config.locals.jwt_issuer
    JWT_AUDIENCE                     = local.env_config.locals.jwt_audience
    AUTH_SERVICE_JWT_SECRET_ID       = dependency.authorizer_secrets.outputs.secret_names["auth-service-jwt-secret"]
    PLATFORM_TRUSTED_PROXY_SECRET_ID = dependency.authorizer_secrets.outputs.secret_names["platform-trusted-proxy-secret"]
    SECRET_CACHE_TTL_SECONDS         = "300"
  }

  managed_policy_arns = [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  ]

  inline_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadAuthorizerRuntimeSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = [dependency.authorizer_secrets.outputs.secret_arns["auth-service-jwt-secret"], dependency.authorizer_secrets.outputs.secret_arns["platform-trusted-proxy-secret"]]
      }
    ]
  })
}
