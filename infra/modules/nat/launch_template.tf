locals {
  private_source_cidrs = length(var.private_subnet_cidrs) > 0 ? var.private_subnet_cidrs : compact([var.private_subnet_cidr])
}

resource "aws_security_group" "nat" {
  name        = "${var.name_prefix}-nat-sg"
  description = "NAT/jump host SG: SSH only from your IP; allow forwarding traffic from private subnet."
  vpc_id      = var.vpc_id

  ingress {
    description = "SSH from workstation"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  dynamic "ingress" {
    for_each = local.private_source_cidrs

    content {
      description = "Forwarded traffic from private subnet"
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    "Name" = "${var.name_prefix}-nat-sg"
  })
}

locals {
  nat_tags = merge(var.tags, { Name = "${var.name_prefix}-nat-instance", Role = "nat", NatSlot = var.availability_zone })
  bootstrap = templatefile("${path.module}/user_data.sh.tftpl", {
    private_subnet_cidrs = local.private_source_cidrs
  })
}

resource "aws_launch_template" "nat" {
  name_prefix   = "${var.name_prefix}-nat-"
  image_id      = data.aws_ami.al2023.id
  instance_type = var.instance_type
  key_name      = var.key_name
  user_data     = base64encode(local.bootstrap)

  credit_specification { cpu_credits = "standard" }

  dynamic "iam_instance_profile" {
    for_each = var.enable_ssm ? [1] : []
    content { arn = aws_iam_instance_profile.ssm[0].arn }
  }
  network_interfaces {
    device_index                = 0
    associate_public_ip_address = true
    delete_on_termination       = true
    security_groups             = [aws_security_group.nat.id]
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 8
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  dynamic "tag_specifications" {
    for_each = toset(["instance", "volume", "network-interface"])
    content {
      resource_type = tag_specifications.value
      tags          = local.nat_tags
    }
  }
  tags = local.nat_tags
}
