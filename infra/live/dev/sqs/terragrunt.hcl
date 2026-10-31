include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

locals {
  env_config   = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  project_name = local.env_config.locals.project_name
  environment  = local.env_config.locals.environment
}
terraform { source = "../../../modules/sqs" }
dependency "event_encryption" {
  config_path = "../event-encryption"
  mock_outputs = {
    key_arn = "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000000"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

inputs = {
  event_kms_key_arn = dependency.event_encryption.outputs.key_arn
  queues = {
    "${local.project_name}-${local.environment}-shipment-events-queue" = {
      dlq_name                   = "${local.project_name}-${local.environment}-shipment-events-dlq"
      visibility_timeout_seconds = 60
      message_retention_seconds  = 345600
      receive_wait_time_seconds  = 20
      create_dlq                 = true
      max_receive_count          = 5
    }
    "${local.project_name}-${local.environment}-shipment-delivery-dlq" = {
      message_retention_seconds = 1209600
      receive_wait_time_seconds = 20
      create_dlq                = false
    }
  }
}
