include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}
terraform { source = "../../../modules/observability" }
locals {
  env  = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  name = "${local.env.locals.project_name}-${local.env.locals.environment}"
}
dependency "eks" {
  config_path = "../eks"
  mock_outputs = {
    cluster_name      = "static-preflight-cluster"
    oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/EXAMPLE"
    oidc_provider_url = "https://oidc.eks.us-east-1.amazonaws.com/id/EXAMPLE"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}
dependency "api" {
  config_path                             = "../apigateway-core"
  mock_outputs                            = { api_id = "preflight" }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}
dependency "rds" {
  config_path                             = "../rds"
  mock_outputs                            = { db_instance_id = "preflight" }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}
inputs = {
  permissions_boundary = "arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-app-workload-boundary"
  cluster_name         = dependency.eks.outputs.cluster_name
  oidc_provider_arn    = dependency.eks.outputs.oidc_provider_arn
  oidc_provider_url    = dependency.eks.outputs.oidc_provider_url
  api_id               = dependency.api.outputs.api_id
  db_instance_id       = dependency.rds.outputs.db_instance_id
  queue_names = {
    shipment     = "${local.name}-shipment-events-queue"
    consumer_dlq = "${local.name}-shipment-events-dlq"
    delivery_dlq = "${local.name}-shipment-delivery-dlq"
  }
}
