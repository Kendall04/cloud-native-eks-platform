resource "aws_cloudwatch_event_rule" "launch" {
  count = local.recovery_count
  name  = local.recovery_name
  state = var.recovery_enabled ? "ENABLED" : "DISABLED"
  event_pattern = jsonencode({
    account       = [data.aws_caller_identity.current.account_id]
    region        = [var.region]
    source        = ["aws.autoscaling"]
    "detail-type" = ["EC2 Instance Launch Successful"]
    detail        = { AutoScalingGroupName = [for slot in local.recovery_config.slots : slot.asg] }
  })
  tags = var.tags
}

resource "aws_sqs_queue_policy" "failures" {
  count     = local.recovery_count
  queue_url = aws_sqs_queue.failures[0].url
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage", Resource = aws_sqs_queue.failures[0].arn,
    Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.launch[0].arn }, StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } } },
    { Effect = "Deny", Principal = "*", Action = "sqs:*", Resource = aws_sqs_queue.failures[0].arn, Condition = { Bool = { "aws:SecureTransport" = "false" } } }
  ] })
}

resource "aws_cloudwatch_event_target" "recovery" {
  count     = local.recovery_count
  rule      = aws_cloudwatch_event_rule.launch[0].name
  arn       = aws_lambda_function.recovery[0].arn
  target_id = "fixed-nat-recovery"
  retry_policy {
    maximum_retry_attempts       = 3
    maximum_event_age_in_seconds = 900
  }
  dead_letter_config { arn = aws_sqs_queue.failures[0].arn }
  depends_on = [aws_sqs_queue_policy.failures]
}

resource "aws_lambda_permission" "events" {
  count          = local.recovery_count
  statement_id   = "ExactLaunchRule"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.recovery[0].function_name
  principal      = "events.amazonaws.com"
  source_arn     = aws_cloudwatch_event_rule.launch[0].arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_lambda_function_event_invoke_config" "recovery" {
  count                        = local.recovery_count
  function_name                = aws_lambda_function.recovery[0].function_name
  maximum_retry_attempts       = 1
  maximum_event_age_in_seconds = 900
  destination_config {
    on_failure { destination = aws_sqs_queue.failures[0].arn }
  }
}

resource "aws_cloudwatch_metric_alarm" "recovery_errors" {
  count               = local.recovery_count
  alarm_name          = "${local.recovery_name}-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = local.recovery_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "recovery_failures" {
  count               = local.recovery_count
  alarm_name          = "${local.recovery_name}-failure-backlog"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.failures[0].name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "missing"
  tags                = var.tags
}
