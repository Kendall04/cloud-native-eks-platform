locals {
  common_tags = merge(var.tags, { Module = "iam" })

  managed_policy_attachments = {
    for attachment in flatten([
      for role_name, role in var.roles : [
        for policy_arn in role.managed_policy_arns : {
          key        = "${role_name}-${md5(policy_arn)}"
          role_name  = role_name
          policy_arn = policy_arn
        }
      ]
    ]) : attachment.key => attachment
  }

  inline_policies = {
    for policy in flatten([
      for role_name, role in var.roles : [
        for policy_name, document in role.inline_policies : {
          key         = "${role_name}-${policy_name}"
          role_name   = role_name
          policy_name = policy_name
          document    = document
        }
      ]
    ]) : policy.key => policy
  }
}

resource "aws_iam_role" "this" {
  for_each = var.roles

  name                 = each.key
  description          = each.value.description
  assume_role_policy   = each.value.assume_role_policy
  max_session_duration = each.value.max_session_duration
  path                 = each.value.path
  permissions_boundary = each.value.permissions_boundary

  tags = merge(local.common_tags, each.value.tags, {
    Name = each.key
  })
}

resource "aws_iam_role_policy_attachment" "this" {
  for_each = local.managed_policy_attachments

  role       = aws_iam_role.this[each.value.role_name].name
  policy_arn = each.value.policy_arn
}

resource "aws_iam_role_policy" "this" {
  for_each = local.inline_policies

  name   = each.value.policy_name
  role   = aws_iam_role.this[each.value.role_name].id
  policy = each.value.document
}

