locals {
  name        = coalesce(var.name, "${var.project_name}-${var.environment}-db")
  common_tags = merge(var.tags, { Module = "rds" })
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.name}-subnets"
  subnet_ids = var.subnet_ids

  tags = merge(local.common_tags, {
    Name = "${local.name}-subnets"
  })
}

resource "aws_security_group" "this" {
  name        = "${local.name}-sg"
  description = "Security group for ${local.name}."
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, {
    Name = "${local.name}-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "cidr" {
  for_each = toset(var.allowed_cidr_blocks)

  security_group_id = aws_security_group.this.id
  cidr_ipv4         = each.value
  from_port         = var.port
  to_port           = var.port
  ip_protocol       = "tcp"
  description       = "Database access from approved CIDR ranges."
}

resource "aws_vpc_security_group_ingress_rule" "security_group" {
  for_each = toset(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.this.id
  referenced_security_group_id = each.value
  from_port                    = var.port
  to_port                      = var.port
  ip_protocol                  = "tcp"
  description                  = "Database access from approved security groups."
}

# No database-initiated network connections are implemented. Security groups
# are stateful: replies to allowed PostgreSQL ingress need no outbound rule.
# The AWS provider removes the default allow-all egress on SG creation.

resource "aws_db_parameter_group" "tls" {
  name_prefix = "${local.name}-tls-"
  family      = "postgres15"
  description = "Require encrypted PostgreSQL connections."
  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
  # RDS restricts session changes to these settings. Keep password-bearing
  # bootstrap parameters out of server logs through the parameter group.
  dynamic "parameter" {
    for_each = toset(["log_parameter_max_length", "log_parameter_max_length_on_error"])
    content {
      name         = parameter.value
      value        = "0"
      apply_method = "immediate"
    }
  }
  tags = local.common_tags
  lifecycle { create_before_destroy = true }
}

resource "aws_db_instance" "this" {
  identifier                      = local.name
  parameter_group_name            = aws_db_parameter_group.tls.name
  engine                          = var.engine
  engine_version                  = var.engine_version
  instance_class                  = var.instance_class
  allocated_storage               = var.allocated_storage
  max_allocated_storage           = var.max_allocated_storage
  storage_type                    = var.storage_type
  storage_encrypted               = var.storage_encrypted
  db_name                         = var.database_name
  username                        = var.username
  password                        = var.manage_master_user_password ? null : var.password
  manage_master_user_password     = var.manage_master_user_password
  port                            = var.port
  db_subnet_group_name            = aws_db_subnet_group.this.name
  vpc_security_group_ids          = [aws_security_group.this.id]
  publicly_accessible             = var.publicly_accessible
  multi_az                        = var.multi_az
  backup_retention_period         = var.backup_retention_period
  backup_window                   = var.backup_window
  maintenance_window              = var.maintenance_window
  apply_immediately               = var.apply_immediately
  performance_insights_enabled    = var.performance_insights_enabled
  deletion_protection             = var.teardown == null ? var.deletion_protection : false
  skip_final_snapshot             = var.teardown == null ? var.skip_final_snapshot : var.teardown.decision == "PURGE_DATABASE_EVIDENCE"
  final_snapshot_identifier       = var.teardown == null ? (var.skip_final_snapshot ? null : coalesce(var.final_snapshot_identifier, "${local.name}-final")) : var.teardown.final_snapshot_identifier
  delete_automated_backups        = var.teardown == null ? true : var.teardown.delete_automated_backups
  enabled_cloudwatch_logs_exports = var.enabled_cloudwatch_logs_exports
  copy_tags_to_snapshot           = true
  auto_minor_version_upgrade      = true

  tags = merge(local.common_tags, {
    Name = local.name
  })
}

