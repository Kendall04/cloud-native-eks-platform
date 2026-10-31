# Offline provider mocks: never contact AWS or apply infrastructure.
mock_provider "aws" {
  mock_data "aws_lb" {
    defaults = {
      arn                = "arn:aws:elasticloadbalancing:us-east-1:999988887777:loadbalancer/app/test/abcdef1234567890"
      vpc_id             = "vpc-abcdef123456789ab"
      internal           = true
      load_balancer_type = "application"
      security_groups    = ["sg-abcdef123456789ab"]
    }
  }
  mock_data "aws_lb_listener" {
    defaults = {
      arn      = "arn:aws:elasticloadbalancing:us-east-1:999988887777:listener/app/test/abcdef1234567890/abcdef1234567890"
      protocol = "HTTP"
      port     = 80
    }
  }
}
variables {
  project_name               = "test"
  environment                = "test"
  region                     = "us-east-1"
  api_id                     = "testapi"
  vpc_link_id                = "testlink"
  authorizer_id              = "testauthorizer"
  vpc_id                     = "vpc-abcdef123456789ab"
  frontend_security_group_id = "sg-abcdef123456789ab"
  alb_discovery_tags = {
    "elbv2.k8s.aws/cluster" = "test-cluster"
    "ingress.k8s.aws/stack" = "test"
    Project                 = "test"
    Environment             = "test"
  }
  protected_route_keys = ["POST /admin/tracking-events"]
}
run "expected_discovery" {
  command = plan
  assert {
    condition     = aws_apigatewayv2_integration.protected[0].integration_uri == data.aws_lb_listener.ingress[0].arn
    error_message = "Integration must use the discovered listener."
  }
  assert {
    condition     = aws_apigatewayv2_route.this["POST /admin/tracking-events"].authorization_type == "CUSTOM"
    error_message = "R1 authorization must remain intact."
  }
}
run "wrong_vpc_rejected" {
  command = plan
  variables { vpc_id = "vpc-bcdef123456789abc" }
  expect_failures = [data.aws_lb.ingress_by_tags]
}
run "wrong_frontend_rejected" {
  command = plan
  variables { frontend_security_group_id = "sg-bcdef123456789abc" }
  expect_failures = [data.aws_lb.ingress_by_tags]
}
run "wrong_listener_rejected" {
  command = plan
  override_data {
    target = data.aws_lb_listener.ingress[0]
    values = { protocol = "HTTPS", port = 443 }
  }
  expect_failures = [data.aws_lb_listener.ingress]
}
run "missing_tag_rejected" {
  command = plan
  variables { alb_discovery_tags = { Project = "test" } }
  expect_failures = [var.alb_discovery_tags]
}
