locals {
  name                = coalesce(var.name, "${var.project_name}-${var.environment}-api")
  common_tags         = merge(var.tags, { Module = "apigateway-core" })
  stage_name_for_tags = replace(var.stage_name, "$", "")
}

resource "aws_security_group" "vpc_link" {
  name        = "${local.name}-vpc-link"
  description = "Security group for API Gateway VPC Link ${local.name}."
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, {
    Name = "${local.name}-vpc-link"
  })
}

resource "aws_security_group" "alb_frontend" {
  name        = "${var.project_name}-${var.environment}-alb-frontend"
  description = "Terraform-owned frontend for the LBC-owned internal ALB."
  vpc_id      = var.vpc_id
  tags        = merge(local.common_tags, { Name = "${var.project_name}-${var.environment}-alb-frontend" })
}
resource "aws_vpc_security_group_egress_rule" "vpc_link_http_to_alb" {
  security_group_id            = aws_security_group.vpc_link.id
  referenced_security_group_id = aws_security_group.alb_frontend.id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}
resource "aws_vpc_security_group_ingress_rule" "alb_from_vpc_link" {
  security_group_id            = aws_security_group.alb_frontend.id
  referenced_security_group_id = aws_security_group.vpc_link.id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}
# No frontend egress is needed: LBC attaches its shared backend SG to the ALB
# and owns backend egress + node/ENI ingress rules. Do not duplicate those here.

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/apigateway/${local.name}"
  retention_in_days = var.access_log_retention_in_days

  tags = merge(local.common_tags, {
    Name = "/aws/apigateway/${local.name}"
  })
}

resource "aws_apigatewayv2_api" "this" {
  name          = local.name
  description   = var.description
  protocol_type = var.protocol_type

  dynamic "cors_configuration" {
    for_each = var.protocol_type == "HTTP" ? [var.cors_configuration] : []

    content {
      allow_origins     = cors_configuration.value.allow_origins
      allow_methods     = cors_configuration.value.allow_methods
      allow_headers     = cors_configuration.value.allow_headers
      expose_headers    = cors_configuration.value.expose_headers
      allow_credentials = cors_configuration.value.allow_credentials
      max_age           = cors_configuration.value.max_age
    }
  }

  tags = merge(local.common_tags, {
    Name = local.name
  })
}

resource "aws_apigatewayv2_vpc_link" "this" {
  name               = "${local.name}-vpc-link"
  subnet_ids         = var.vpc_link_subnet_ids
  security_group_ids = [aws_security_group.vpc_link.id]

  tags = merge(local.common_tags, {
    Name = "${local.name}-vpc-link"
  })
}

resource "aws_lambda_permission" "authorizer" {
  statement_id  = "AllowApiGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = var.jwt_authorizer_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/authorizers/*"
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id                            = aws_apigatewayv2_api.this.id
  name                              = "${local.name}-jwt-request-authorizer"
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = var.jwt_authorizer_lambda_invoke_arn
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
  identity_sources                  = var.jwt_authorizer_identity_sources
  authorizer_result_ttl_in_seconds  = var.jwt_authorizer_result_ttl_in_seconds

  depends_on = [aws_lambda_permission.authorizer]
}

resource "aws_apigatewayv2_stage" "this" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = var.stage_name
  auto_deploy = var.auto_deploy

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.this.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      sourceIp         = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      protocol         = "$context.protocol"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      responseLength   = "$context.responseLength"
      integrationError = "$context.integrationErrorMessage"
    })
  }

  default_route_settings {
    detailed_metrics_enabled = true
    throttling_burst_limit   = 100
    throttling_rate_limit    = 50
  }

  tags = merge(local.common_tags, {
    Name = "${local.name}-${local.stage_name_for_tags}"
  })
}
