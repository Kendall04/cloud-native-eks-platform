locals {
  metric_widgets = [
    { title = "Edge requests / 4xx / 5xx", stat = "Sum", metrics = [for n in ["Count", "4xx", "5xx"] : ["AWS/ApiGateway", n, "ApiId", var.api_id]] },
    { title = "Edge latency / integration latency (ms)", stat = "Average", metrics = [for n in ["Latency", "IntegrationLatency"] : ["AWS/ApiGateway", n, "ApiId", var.api_id]] },
    { title = "SQS visible / in-flight / delayed", stat = "Maximum", metrics = [for n in ["ApproximateNumberOfMessagesVisible", "ApproximateNumberOfMessagesNotVisible", "ApproximateNumberOfMessagesDelayed"] : ["AWS/SQS", n, "QueueName", var.queue_names.shipment]] },
    { title = "SQS age (seconds)", stat = "Maximum", metrics = [["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", var.queue_names.shipment]] },
    { title = "Consumer / EventBridge delivery DLQs", stat = "Maximum", metrics = [for q in [var.queue_names.consumer_dlq, var.queue_names.delivery_dlq] : ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", q]] },
    { title = "Outbox pending / failed", stat = "Maximum", metrics = [for n in ["tracking.outbox.pending", "tracking.outbox.failed"] : ["Platform/Operations", n, "Environment", var.environment, "Service", "tracking"]] },
    { title = "Oldest outbox age (seconds)", stat = "Maximum", metrics = [["Platform/Operations", "tracking.outbox.oldest_age", "Environment", var.environment, "Service", "tracking"]] },
    { title = "Publish success / failure", stat = "Sum", metrics = [for n in ["tracking.publish.success", "tracking.publish.failure"] : ["Platform/Operations", n, "Environment", var.environment, "Service", "tracking"]] },
    { title = "Consumer applied / duplicate / gap / rejected", stat = "Sum", metrics = [for n in ["applied", "duplicate", "sequence_gap", "rejected"] : ["Platform/Operations", "shipment.consumer.${n}", "Environment", var.environment, "Service", "shipment"]] },
    { title = "RDS CPU / connections", stat = "Average", metrics = [for n in ["CPUUtilization", "DatabaseConnections"] : ["AWS/RDS", n, "DBInstanceIdentifier", var.db_instance_id]] },
    { title = "RDS free storage (bytes)", stat = "Minimum", metrics = [["AWS/RDS", "FreeStorageSpace", "DBInstanceIdentifier", var.db_instance_id]] },
    { title = "RDS read / write latency (seconds)", stat = "Average", metrics = [for n in ["ReadLatency", "WriteLatency"] : ["AWS/RDS", n, "DBInstanceIdentifier", var.db_instance_id]] },
    { title = "Workload HTTP requests / errors", stat = "Sum", metrics = concat([for s in ["auth", "tracking", "shipment"] : ["Platform/Operations", "http.requests", "Environment", var.environment, "Service", s]], [for s in ["auth", "tracking", "shipment"] : ["Platform/Operations", "http.errors", "Environment", var.environment, "Service", s]]) }
    ,
    { title = "Sampled workload HTTP latency p95 (ms)", stat = "p95", metrics = [for s in ["auth", "tracking", "shipment"] : ["Platform/Operations", "http.duration_ms", "Environment", var.environment, "Service", s]] }
  ]
  # OTLP metric names/labels: no Classic ContainerInsights namespace aliases.
  cluster_filter = "\"@resource.k8s.cluster.name\"=\"${var.cluster_name}\""
  promql_widgets = [
    { title = "Deployment desired / available replicas", queries = ["sum by (deployment) (kube_deployment_spec_replicas{${local.cluster_filter},namespace=\"apps\"})", "sum by (deployment) (kube_deployment_status_replicas_available{${local.cluster_filter},namespace=\"apps\"})"] },
    { title = "Pod CPU cores", queries = ["sum by (pod) (rate(container_cpu_usage_seconds_total{${local.cluster_filter},namespace=\"apps\",container!=\"\"}[5m]))"] },
    { title = "Pod memory bytes", queries = ["sum by (pod) (container_memory_working_set_bytes{${local.cluster_filter},namespace=\"apps\",container!=\"\"})"] },
    { title = "Restarts / pending pods", queries = ["sum (increase(kube_pod_container_status_restarts_total{${local.cluster_filter},namespace=\"apps\"}[15m]))", "sum (kube_pod_status_phase{${local.cluster_filter},namespace=\"apps\",phase=\"Pending\"})"] },
    { title = "Node count / available CPU", queries = ["count(kube_node_info{${local.cluster_filter}})", "sum(kube_node_status_allocatable{${local.cluster_filter},resource=\"cpu\"})"] }
  ]
}
resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = local.name
  dashboard_body = jsonencode({ widgets = concat(
    [for i, w in local.metric_widgets : {
      type       = "metric", x = (i % 2) * 12, y = floor(i / 2) * 6, width = 12, height = 6
      properties = merge(w, { region = var.region, period = 60, view = "timeSeries" })
    }],
    [for i, w in local.promql_widgets : {
      type       = "chart", x = (i % 2) * 12, y = 42 + floor(i / 2) * 6, width = 12, height = 6
      properties = { title = w.title, region = var.region, view = "line", data = { queries = [for j, q in w.queries : { id = "q${j}", type = "cloudwatch-metrics", language = "PromQL", query = q }] } }
    }]
  ) })
}
