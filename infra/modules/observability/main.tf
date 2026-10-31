locals {
  name   = "${var.project_name}-${var.environment}"
  prefix = "/aws/containerinsights/${var.cluster_name}"
}
resource "aws_cloudwatch_log_group" "containers" {
  for_each          = toset(["application", "host", "dataplane", "performance"])
  name              = "${local.prefix}/${each.value}"
  retention_in_days = 14
}
resource "aws_iam_role" "agent" {
  name                 = "${local.name}-cloudwatch-irsa"
  permissions_boundary = var.permissions_boundary
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = var.oidc_provider_arn }
      Condition = { StringEquals = {
        "${replace(var.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
        "${replace(var.oidc_provider_url, "https://", "")}:sub" = [
          "system:serviceaccount:amazon-cloudwatch:cloudwatch-agent",
          "system:serviceaccount:amazon-cloudwatch:fluent-bit"
        ]
      } }
    }]
  })
}
resource "aws_iam_role_policy" "agent" {
  name = "bounded-telemetry"
  role = aws_iam_role.agent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], Resource = [for group in aws_cloudwatch_log_group.containers : "${group.arn}:*"] },
      { Effect = "Allow", Action = ["logs:DescribeLogGroups", "ec2:DescribeVolumes", "ec2:DescribeTags"], Resource = "*" },
      # OTLP ingestion has no resource-level ARN; only the telemetry IRSA role receives it.
      { Effect = "Allow", Action = ["cloudwatch:PutMetricData"], Resource = "*" }
    ]
  })
}
resource "aws_eks_addon" "cloudwatch" {
  cluster_name                = var.cluster_name
  addon_name                  = "amazon-cloudwatch-observability"
  addon_version               = var.addon_version
  service_account_role_arn    = aws_iam_role.agent.arn
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  configuration_values = jsonencode({
    otelContainerInsights = { enabled = true, logs = { enabled = false }, metricResolution = "60s" }
    manager               = { applicationSignals = { autoMonitor = { monitorAllServices = false } } }
    containerInsights     = { enabled = false }
    applicationSignals    = { enabled = false }
    containerLogs = {
      enabled = true
      fluentBit = { config = { extraFiles = {
        # Override only application logs. Preserve raw JSON so _aws remains the
        # EMF root; never wrap EMF under log_processed or a Console message field.
        "application-log.conf" = <<-CONFIG
          [INPUT]
              Name tail
              Tag application.*
              Path /var/log/containers/*.log
              multiline.parser docker, cri
              DB /var/fluent-bit/state/flb_container.db
              Mem_Buf_Limit 50MB
              Skip_Long_Lines On
              Read_from_Head Off
          [OUTPUT]
              Name cloudwatch_logs
              Match application.*
              region ${var.region}
              log_group_name ${local.prefix}/application
              log_stream_prefix $${HOST_NAME}-
              auto_create_group false
              log_key log
              log_format json/emf
        CONFIG
      } } }
    }
  })
  depends_on = [aws_iam_role_policy.agent, aws_cloudwatch_log_group.containers]
}
output "addon_version" { value = aws_eks_addon.cloudwatch.addon_version }
