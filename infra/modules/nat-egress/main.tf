locals {
  use_shared_private_route_table = length(var.private_route_table_ids) == 1

  nat_instances = var.nat_mode == "instance" ? (
    local.use_shared_private_route_table ? {
      (var.availability_zones[0]) = {
        public_subnet_id     = var.public_subnet_ids[0]
        private_subnet_cidrs = var.private_subnet_cidrs
      }
      } : {
      for index, az in var.availability_zones : az => {
        public_subnet_id     = var.public_subnet_ids[index]
        private_subnet_cidrs = [var.private_subnet_cidrs[index]]
      }
    }
  ) : {}

  route_targets = {
    for index, route_table_id in var.private_route_table_ids : tostring(index) => {
      route_table_id = route_table_id
      nat_gateway_id = var.nat_mode == "gateway" ? var.nat_gateway_ids[length(var.nat_gateway_ids) == 1 ? 0 : index] : null
    }
  }
}

module "instance" {
  for_each = local.nat_instances

  source = "../nat"

  name_prefix          = "${var.name_prefix}-${each.key}"
  vpc_id               = var.vpc_id
  public_subnet_id     = each.value.public_subnet_id
  availability_zone    = each.key
  instance_type        = var.instance_type
  ami_id               = var.ami_id
  key_name             = var.key_name
  allowed_ssh_cidr     = var.allowed_ssh_cidr
  private_subnet_cidr  = each.value.private_subnet_cidrs[0]
  private_subnet_cidrs = each.value.private_subnet_cidrs
  enable_ssm           = var.enable_ssm
  tags = merge(var.tags, {
    Project          = var.project_name
    Environment      = var.environment
    AvailabilityZone = each.key
  })
}

resource "aws_route" "default" {
  for_each = var.nat_mode == "gateway" ? local.route_targets : {}

  route_table_id         = each.value.route_table_id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = each.value.nat_gateway_id
}
