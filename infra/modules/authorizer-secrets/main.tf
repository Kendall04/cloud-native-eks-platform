locals {
  common_tags = merge(var.tags, { Module = "authorizer-secrets" })
}

resource "aws_secretsmanager_secret" "this" {
  for_each = var.secrets

  name                    = each.value.name
  description             = each.value.description
  recovery_window_in_days = each.value.recovery_window_in_days
  kms_key_id              = each.value.kms_key_id

  tags = merge(local.common_tags, {
    Name = each.value.name
  })
}
