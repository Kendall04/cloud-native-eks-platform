include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config                    = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name                  = local.env_config.locals.project_name
  environment                   = local.env_config.locals.environment
  enable_apigateway_integration = try(local.env_config.locals.enable_apigateway_integration, false)
}

terraform {
  source = "../../../modules/apigateway-integration"
}

dependency "apigateway_core" {
  config_path = "../apigateway-core"

  mock_outputs = {
    api_id                         = "a1b2c3d4"
    vpc_link_id                    = "vpclink-1234567890"
    vpc_link_security_group_id     = "sg-00000000000000000"
    authorizer_id                  = "authorizer-1234567890"
    alb_frontend_security_group_id = "sg-00000000000000000"
  }

  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "vpc" {
  config_path                             = "../vpc"
  mock_outputs                            = { vpc_id = "vpc-00000000000000000" }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

inputs = {
  vpc_id                     = dependency.vpc.outputs.vpc_id
  frontend_security_group_id = dependency.apigateway_core.outputs.alb_frontend_security_group_id
  enabled                    = local.enable_apigateway_integration
  api_id                     = dependency.apigateway_core.outputs.api_id
  vpc_link_id                = dependency.apigateway_core.outputs.vpc_link_id
  authorizer_id              = dependency.apigateway_core.outputs.authorizer_id
  alb_listener_port          = 80

  alb_discovery_tags = {
    "ingress.k8s.aws/stack" = local.project_name
    "elbv2.k8s.aws/cluster" = local.env_config.locals.eks_cluster_name
    Project                 = local.project_name
    Environment             = local.environment
  }

  public_route_keys = [
    "POST /auth/login",
    "POST /auth/register",
    "POST /auth/refresh"
  ]

  protected_route_keys = [
    "GET /auth/me",
    "GET /auth/validate",
    "POST /shipments",
    "GET /shipments",
    "GET /shipments/by-id/{id}",
    "GET /shipments/by-tracking/{trackingNumber}",
    "GET /tracking/by-shipment/{shipmentId}",
    "GET /tracking/by-tracking-number/{trackingNumber}",
    # JWT is validated at the edge; RequireAdminRole is enforced by tracking-service.
    "POST /admin/tracking-events"
  ]
}
