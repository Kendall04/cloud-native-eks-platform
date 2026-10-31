data "aws_caller_identity" "current" {}

locals {
  recovery_count = var.nat_mode == "instance" ? 1 : 0
  recovery_name  = "${var.name_prefix}-nat-recovery"
  recovery_config = {
    schema      = 1
    account     = data.aws_caller_identity.current.account_id
    region      = var.region
    project     = var.project_name
    environment = var.environment
    vpc         = var.vpc_id
    slots = [for az in sort(keys(local.nat_instances)) : {
      asg              = "${var.name_prefix}-${az}-nat-asg"
      az               = az
      subnet           = local.nat_instances[az].public_subnet_id
      eip              = module.instance[az].eip_allocation_id
      table            = var.private_route_table_ids[local.use_shared_private_route_table ? 0 : index(var.availability_zones, az)]
      ami              = module.instance[az].ami_id
      instance_type    = var.instance_type
      profile          = module.instance[az].instance_profile_arn
      sg               = module.instance[az].security_group_id
      lt               = module.instance[az].launch_template_id
      version          = module.instance[az].launch_template_version
      user_data_sha256 = module.instance[az].user_data_sha256
      predecessor_enis = lookup(var.approved_predecessor_enis, az, [])
    }]
  }
  recovery_generation = sha256(jsonencode(local.recovery_config))
  package_path        = "${path.module}/lambda/recovery.zip"
}

resource "aws_dynamodb_table" "recovery" {
  count                       = local.recovery_count
  name                        = local.recovery_name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  deletion_protection_enabled = true
  attribute {
    name = "pk"
    type = "S"
  }
  server_side_encryption { enabled = true }
  tags = var.tags
  lifecycle { prevent_destroy = true }
}

# Lambda cannot write CONTROL; generation/admission are separately operator-owned.
resource "aws_dynamodb_table_item" "control" {
  count      = local.recovery_count
  table_name = aws_dynamodb_table.recovery[0].name
  hash_key   = "pk"
  item       = jsonencode({ pk = { S = "CONTROL" }, data = { S = jsonencode({ enabled = var.recovery_enabled, generation = local.recovery_generation }) } })
}

resource "aws_cloudwatch_log_group" "recovery" {
  count             = local.recovery_count
  name              = "/aws/lambda/${local.recovery_name}"
  retention_in_days = 7
  tags              = var.tags
}

resource "aws_sqs_queue" "failures" {
  count                     = local.recovery_count
  name                      = "${local.recovery_name}-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = var.tags
  lifecycle { prevent_destroy = true }
}

resource "aws_lambda_function" "recovery" {
  count                          = local.recovery_count
  function_name                  = local.recovery_name
  role                           = aws_iam_role.recovery[0].arn
  runtime                        = "python3.13"
  handler                        = "recovery.lambda_handler"
  filename                       = local.package_path
  source_code_hash               = filebase64sha256(local.package_path)
  timeout                        = 180
  memory_size                    = 128
  reserved_concurrent_executions = var.recovery_enabled ? 1 : 0
  environment {
    variables = {
      NAT_CONFIG        = jsonencode(local.recovery_config)
      NAT_GENERATION    = local.recovery_generation
      NAT_JOURNAL_TABLE = aws_dynamodb_table.recovery[0].name
    }
  }
  tags       = var.tags
  depends_on = [aws_cloudwatch_log_group.recovery, aws_iam_role_policy.recovery]
  lifecycle {
    precondition {
      condition     = length(jsonencode(local.recovery_config)) + length(local.recovery_generation) + length(aws_dynamodb_table.recovery[0].name) + 70 < 4096
      error_message = "Pinned NAT configuration must fit the Lambda environment limit."
    }
  }
}
