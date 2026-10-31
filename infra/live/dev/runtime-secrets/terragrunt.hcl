include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}
terraform { source = "../../../modules/runtime-secrets" }
dependency "eks" {
  config_path = "../eks"
  mock_outputs = {
    oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/EXAMPLE"
    oidc_provider_url = "https://oidc.eks.us-east-1.amazonaws.com/id/EXAMPLE"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}
dependency "shared" {
  config_path = "../api-gateway-authorizer-secrets"
  mock_outputs = { secret_arns = {
    auth-service-jwt-secret       = "arn:aws:secretsmanager:us-east-1:123456789012:secret:mock-jwt"
    platform-trusted-proxy-secret = "arn:aws:secretsmanager:us-east-1:123456789012:secret:mock-proxy"
  } }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}
inputs = {
  permissions_boundary = "arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-app-workload-boundary"
  oidc_provider_arn    = dependency.eks.outputs.oidc_provider_arn
  oidc_provider_url    = dependency.eks.outputs.oidc_provider_url
  shared_secret_arns = {
    auth-jwt      = dependency.shared.outputs.secret_arns["auth-service-jwt-secret"]
    gateway-trust = dependency.shared.outputs.secret_arns["platform-trusted-proxy-secret"]
  }
}
