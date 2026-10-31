locals {
  common_tags = merge(var.tags, { Module = "apigateway-integration" })
  public_routes = {
    for route_key in var.public_route_keys : route_key => "public"
  }
  protected_routes = {
    for route_key in var.protected_route_keys : route_key => "protected"
  }
  routes = merge(local.public_routes, local.protected_routes)
  protected_request_parameters = {
    "overwrite:header.X-Platform-User-Id"      = "$context.authorizer.userId"
    "overwrite:header.X-Platform-Email"        = "$context.authorizer.email"
    "overwrite:header.X-Platform-Roles"        = "$context.authorizer.roles"
    "overwrite:header.X-Platform-Proxy-Secret" = "$context.authorizer.proxySecret"
  }
  alb_arn          = var.enabled ? data.aws_lb.ingress_by_tags[0].arn : null
  alb_listener_arn = var.enabled ? data.aws_lb_listener.ingress[0].arn : null
}

# aws_lb's provider implementation fails unless tags match exactly one result.
data "aws_lb" "ingress_by_tags" {
  count = var.enabled ? 1 : 0
  tags  = var.alb_discovery_tags
  lifecycle {
    postcondition {
      condition     = self.vpc_id == var.vpc_id && self.internal && self.load_balancer_type == "application" && contains(self.security_groups, var.frontend_security_group_id)
      error_message = "Phase 4 prerequisite failed: expected one internal application ALB in the environment VPC with the Terraform frontend SG."
    }
  }
}
# AWS allows one listener per port; the provider enforces a single match.
data "aws_lb_listener" "ingress" {
  count             = var.enabled ? 1 : 0
  load_balancer_arn = data.aws_lb.ingress_by_tags[0].arn
  port              = var.alb_listener_port
  lifecycle {
    postcondition {
      condition     = self.protocol == "HTTP" && self.port == 80
      error_message = "Phase 4 prerequisite failed: expected HTTP listener on port 80."
    }
  }
}

resource "aws_apigatewayv2_integration" "public" {
  count                  = var.enabled ? 1 : 0
  api_id                 = var.api_id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = local.alb_listener_arn
  connection_type        = "VPC_LINK"
  connection_id          = var.vpc_link_id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
  description            = "Public ALB integration for unauthenticated auth routes."
}

resource "aws_apigatewayv2_integration" "protected" {
  count                  = var.enabled ? 1 : 0
  api_id                 = var.api_id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = local.alb_listener_arn
  connection_type        = "VPC_LINK"
  connection_id          = var.vpc_link_id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
  description            = "Protected ALB integration that injects API-Gateway-verified identity headers."
  request_parameters     = local.protected_request_parameters
}

resource "aws_apigatewayv2_route" "this" {
  for_each = var.enabled ? local.routes : {}

  api_id    = var.api_id
  route_key = each.key
  target = format(
    "integrations/%s",
  each.value == "protected" ? aws_apigatewayv2_integration.protected[0].id : aws_apigatewayv2_integration.public[0].id)
  authorization_type = each.value == "protected" ? "CUSTOM" : "NONE"
  authorizer_id      = each.value == "protected" ? var.authorizer_id : null
}
