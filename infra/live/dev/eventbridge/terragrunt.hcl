include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config                 = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name               = local.env_config.locals.project_name
  environment                = local.env_config.locals.environment
  shipment_events_queue_name = "${local.project_name}-${local.environment}-shipment-events-queue"
  delivery_dlq_name          = "${local.project_name}-${local.environment}-shipment-delivery-dlq"
}
terraform { source = "../../../modules/eventbridge" }
dependency "sqs" {
  config_path = "../sqs"
  mock_outputs = {
    queue_arns = {
      "${local.shipment_events_queue_name}" = "arn:aws:sqs:us-east-1:123456789012:${local.shipment_events_queue_name}"
      "${local.delivery_dlq_name}"          = "arn:aws:sqs:us-east-1:123456789012:${local.delivery_dlq_name}"
    }
    queue_urls = {
      "${local.shipment_events_queue_name}" = "https://sqs.us-east-1.amazonaws.com/123456789012/${local.shipment_events_queue_name}"
      "${local.delivery_dlq_name}"          = "https://sqs.us-east-1.amazonaws.com/123456789012/${local.delivery_dlq_name}"
    }
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}
inputs = {
  event_bus_name = "${local.project_name}-${local.environment}-bus"
  rules = {
    trk-upd-shipment = {
      description                  = "Routes TrackingStatusUpdated to shipment; separate delivery and consumer failures."
      event_pattern                = jsonencode({ source = ["tracking-service"], "detail-type" = ["TrackingStatusUpdated"] })
      target_queue_arn             = dependency.sqs.outputs.queue_arns[local.shipment_events_queue_name]
      target_queue_url             = dependency.sqs.outputs.queue_urls[local.shipment_events_queue_name]
      delivery_dlq_arn             = dependency.sqs.outputs.queue_arns[local.delivery_dlq_name]
      delivery_dlq_url             = dependency.sqs.outputs.queue_urls[local.delivery_dlq_name]
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 10
      input_path                   = "$.detail"
    }
  }
}
