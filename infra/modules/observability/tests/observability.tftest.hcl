mock_provider "aws" {}
variables {
  project_name      = "fixture"
  environment       = "dev"
  region            = "us-east-1"
  cluster_name      = "fixture-dev"
  oidc_provider_arn = "arn:aws:iam::999988887777:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/TEST"
  oidc_provider_url = "https://oidc.eks.us-east-1.amazonaws.com/id/TEST"
  api_id            = "fixture"
  db_instance_id    = "fixture"
  queue_names       = { shipment = "fixture-queue", consumer_dlq = "fixture-dlq", delivery_dlq = "fixture-delivery-dlq" }
}
run "bounded_observability" {
  command = plan
  assert {
    condition     = alltrue([for g in aws_cloudwatch_log_group.containers : g.retention_in_days == 14])
    error_message = "All container log groups require bounded retention."
  }
  assert {
    condition     = jsondecode(aws_eks_addon.cloudwatch.configuration_values).otelContainerInsights.enabled && !jsondecode(aws_eks_addon.cloudwatch.configuration_values).containerInsights.enabled && !jsondecode(aws_eks_addon.cloudwatch.configuration_values).applicationSignals.enabled
    error_message = "OTel only, no duplicate Classic or Application Signals."
  }
  assert {
    condition     = aws_eks_addon.cloudwatch.addon_version == "v6.2.0-eksbuild.1" && length(aws_cloudwatch_metric_alarm.operations) == 6
    error_message = "Reviewed addon and six workload alarms required."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.operations["consumer-dlq"].threshold == 0 && aws_cloudwatch_metric_alarm.operations["delivery-dlq"].threshold == 0
    error_message = "Both delivery and processing DLQs must alarm."
  }
  assert {
    condition     = alltrue([for w in slice(jsondecode(aws_cloudwatch_dashboard.operations.dashboard_body).widgets, 0, 14) : alltrue([for m in w.properties.metrics : length(m) >= 4])])
    error_message = "CloudWatch metrics must be arrays, not flattened strings."
  }
}
