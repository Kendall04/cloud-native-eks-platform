output "api_id" {
  description = "ID of the API Gateway."
  value       = aws_apigatewayv2_api.this.id
}

output "api_endpoint" {
  description = "Base endpoint for the API."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "execution_arn" {
  description = "Execution ARN of the API."
  value       = aws_apigatewayv2_api.this.execution_arn
}

output "vpc_link_id" {
  description = "ID of the API Gateway VPC link."
  value       = aws_apigatewayv2_vpc_link.this.id
}

output "vpc_link_security_group_id" {
  description = "Security group ID attached to the API Gateway VPC link."
  value       = aws_security_group.vpc_link.id
}

output "authorizer_id" {
  description = "ID of the API Gateway request authorizer."
  value       = aws_apigatewayv2_authorizer.jwt.id
}

output "stage_name" {
  description = "Name of the deployed API Gateway stage."
  value       = aws_apigatewayv2_stage.this.name
}

output "stage_invoke_url" {
  description = "Invoke URL of the deployed stage."
  value       = var.stage_name == "$default" ? aws_apigatewayv2_api.this.api_endpoint : "${aws_apigatewayv2_api.this.api_endpoint}/${aws_apigatewayv2_stage.this.name}"
}

output "alb_frontend_security_group_id" { value = aws_security_group.alb_frontend.id }
