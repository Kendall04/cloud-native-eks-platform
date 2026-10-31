resource "aws_autoscaling_group" "nat" {
  for_each = local.nat_instances

  name                      = "${var.name_prefix}-${each.key}-nat-asg"
  min_size                  = var.recovery_enabled ? 1 : 0
  max_size                  = var.recovery_enabled ? 1 : 0
  desired_capacity          = var.recovery_enabled ? 1 : 0
  vpc_zone_identifier       = [each.value.public_subnet_id]
  health_check_type         = "EC2"
  health_check_grace_period = 300
  wait_for_capacity_timeout = "0"

  # Terminate before launch; no intentional surge above one NAT per slot.
  instance_maintenance_policy {
    min_healthy_percentage = 0
    max_healthy_percentage = 100
  }
  launch_template {
    id      = module.instance[each.key].launch_template_id
    version = tostring(module.instance[each.key].launch_template_version)
  }
  dynamic "tag" {
    for_each = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-nat-instance", Project = var.project_name, Environment = var.environment, Role = "nat", NatSlot = each.key })
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

  depends_on = [aws_cloudwatch_event_target.recovery, aws_lambda_permission.events, aws_lambda_function_event_invoke_config.recovery, aws_dynamodb_table_item.control]
}
