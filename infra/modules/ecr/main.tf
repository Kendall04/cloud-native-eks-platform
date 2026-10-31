locals {
  common_tags = merge(var.tags, { Module = "ecr" })

  repository_configs = {
    for name, repository in var.repositories : name => merge(repository, {
      lifecycle_policy = repository.lifecycle_policy != null ? repository.lifecycle_policy : var.default_lifecycle_policy
    })
  }
}

resource "aws_ecr_repository" "this" {
  for_each = local.repository_configs

  name                 = each.key
  image_tag_mutability = each.value.image_tag_mutability
  force_delete         = each.value.force_delete

  image_scanning_configuration {
    scan_on_push = each.value.scan_on_push
  }

  encryption_configuration {
    encryption_type = each.value.encryption_type
    kms_key         = each.value.kms_key
  }

  tags = merge(local.common_tags, {
    Name = each.key
  })
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = {
    for name, repository in local.repository_configs : name => repository
    if repository.lifecycle_policy != null
  }

  repository = aws_ecr_repository.this[each.key].name
  policy     = each.value.lifecycle_policy
}
