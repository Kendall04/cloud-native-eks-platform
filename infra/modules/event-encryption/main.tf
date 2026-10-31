data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "aws_iam_policy_document" "key" {
  statement {
    sid       = "EnableAccountAdministrationAndIAMDelegation"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
  # AWS-documented SQS service-producer policy. SourceArn from the queue policy
  # is deliberately NOT assumed to be present in the KMS request context.
  statement {
    sid       = "AllowEventBridgeDeliveryToEncryptedQueues"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}
resource "aws_kms_key" "events" {
  description              = "${var.project_name} ${var.environment} event pipeline SQS encryption"
  key_usage                = "ENCRYPT_DECRYPT"
  customer_master_key_spec = "SYMMETRIC_DEFAULT"
  enable_key_rotation      = true
  deletion_window_in_days  = 30
  policy                   = data.aws_iam_policy_document.key.json
  tags                     = merge(var.tags, { Module = "event-encryption" })
}
resource "aws_kms_alias" "events" {
  name          = "alias/${var.project_name}-${var.environment}-events"
  target_key_id = aws_kms_key.events.key_id
}
