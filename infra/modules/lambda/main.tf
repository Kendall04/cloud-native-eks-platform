locals {
  common_tags = merge(var.tags, { Module = "lambda" })
}

data "archive_file" "package" {
  type = "zip"
  # Deliberate runtime-provided SDK: only the handler enters the archive.
  # Local node_modules, tests, credentials and generated files cannot enter it.
  source {
    content  = file("${var.source_dir}/src/index.mjs")
    filename = "src/index.mjs"
  }
  output_path = "${path.module}/${var.function_name}.zip"
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  permissions_boundary = var.iam_permissions_boundary_arn
  name                 = "${var.function_name}-role"
  description          = var.description
  assume_role_policy   = data.aws_iam_policy_document.assume_role.json

  tags = merge(local.common_tags, {
    Name = "${var.function_name}-role"
  })
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each = toset(var.managed_policy_arns)

  role       = aws_iam_role.this.name
  policy_arn = each.value
}

resource "aws_iam_role_policy" "inline" {
  count = var.inline_policy_json != null ? 1 : 0

  name   = "${var.function_name}-inline"
  role   = aws_iam_role.this.id
  policy = var.inline_policy_json
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_in_days

  tags = merge(local.common_tags, {
    Name = "/aws/lambda/${var.function_name}"
  })
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  description      = var.description
  role             = aws_iam_role.this.arn
  runtime          = var.runtime
  handler          = var.handler
  timeout          = var.timeout
  memory_size      = var.memory_size
  architectures    = var.architectures
  filename         = data.archive_file.package.output_path
  source_code_hash = data.archive_file.package.output_base64sha256

  dynamic "environment" {
    for_each = length(var.environment_variables) > 0 ? [var.environment_variables] : []

    content {
      variables = environment.value
    }
  }

  tags = merge(local.common_tags, {
    Name = var.function_name
  })

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy_attachment.managed,
    aws_iam_role_policy.inline,
  ]
}

resource "aws_lambda_event_source_mapping" "sqs" {
  for_each = var.sqs_event_sources

  event_source_arn                   = each.value.event_source_arn
  function_name                      = aws_lambda_function.this.arn
  enabled                            = each.value.enabled
  batch_size                         = each.value.batch_size
  maximum_batching_window_in_seconds = each.value.maximum_batching_window_in_seconds
  function_response_types            = ["ReportBatchItemFailures"]

  depends_on = [aws_lambda_function.this]
}
