locals {
  alarms = {
    consumer-dlq  = { namespace = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible", dimensions = { QueueName = var.queue_names.consumer_dlq }, threshold = 0, stat = "Maximum", periods = 1, action = "Consumer poison/gap. Inspect R5 inbox and predecessor before redrive." }
    delivery-dlq  = { namespace = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible", dimensions = { QueueName = var.queue_names.delivery_dlq }, threshold = 0, stat = "Maximum", periods = 1, action = "Delivery failed. Inspect EventBridge target policy and CMK before replay." }
    queue-age     = { namespace = "AWS/SQS", metric = "ApproximateAgeOfOldestMessage", dimensions = { QueueName = var.queue_names.shipment }, threshold = 300, stat = "Maximum", periods = 3, action = "Over five-minute demo processing budget. Check gaps, DB, KEDA and Pending pods." }
    outbox-failed = { namespace = "Platform/Operations", metric = "tracking.outbox.failed", dimensions = { Environment = var.environment, Service = "tracking" }, threshold = 0, stat = "Maximum", periods = 1, action = "Retry budget exhausted. Inspect operator outbox CLI and repair before requeue." }
    outbox-age    = { namespace = "Platform/Operations", metric = "tracking.outbox.oldest_age", dimensions = { Environment = var.environment, Service = "tracking" }, threshold = 300, stat = "Maximum", periods = 3, action = "Publication delayed beyond five minutes. Check IAM, EventBridge and dispatcher logs." }
    rds-cpu       = { namespace = "AWS/RDS", metric = "CPUUtilization", dimensions = { DBInstanceIdentifier = var.db_instance_id }, threshold = 80, stat = "Average", periods = 5, action = "Sustained CPU saturation. Inspect connections, query latency and scale concurrency." }
  }
}
resource "aws_cloudwatch_metric_alarm" "operations" {
  for_each            = local.alarms
  alarm_name          = "${local.name}-${each.key}"
  alarm_description   = each.value.action
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  dimensions          = each.value.dimensions
  comparison_operator = "GreaterThanThreshold"
  threshold           = each.value.threshold
  statistic           = each.value.stat
  period              = 60
  evaluation_periods  = each.value.periods
  treat_missing_data  = "missing"
}
resource "aws_cloudwatch_metric_alarm" "edge_errors" {
  alarm_name          = "${local.name}-edge-5xx"
  alarm_description   = "At least 20 requests/min and >5% 5xx for 3 minutes. Compare IntegrationLatency, pod HTTP errors and RDS before retrying deployments."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 5
  evaluation_periods  = 3
  treat_missing_data  = "missing"
  metric_query {
    id          = "rate"
    expression  = "IF(requests>=20,100*errors/requests,0)"
    return_data = true
  }
  dynamic "metric_query" {
    for_each = { requests = "Count", errors = "5xx" }
    content {
      id          = metric_query.key
      return_data = false
      metric {
        namespace   = "AWS/ApiGateway"
        metric_name = metric_query.value
        dimensions  = { ApiId = var.api_id }
        period      = 60
        stat        = "Sum"
      }
    }
  }
}
