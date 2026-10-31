output "alb_arn" {
  description = "ARN of the ALB targeted by API Gateway."
  value       = local.alb_arn
}

output "alb_listener_arn" {
  description = "ARN of the ALB listener targeted by API Gateway."
  value       = local.alb_listener_arn
}

output "public_integration_id" {
  description = "ID of the public API Gateway integration."
  value       = try(aws_apigatewayv2_integration.public[0].id, null)
}

output "protected_integration_id" {
  description = "ID of the protected API Gateway integration."
  value       = try(aws_apigatewayv2_integration.protected[0].id, null)
}

output "route_ids" {
  description = "IDs of the API Gateway routes created by this module."
  value       = { for route_key, route in aws_apigatewayv2_route.this : route_key => route.id }
}
