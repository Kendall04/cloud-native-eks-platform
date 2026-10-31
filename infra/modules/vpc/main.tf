locals {
  name                      = coalesce(var.name, "${var.project_name}-${var.environment}-vpc")
  common_tags               = merge(var.tags, { Module = "vpc" })
  nat_gateway_count         = var.enable_nat_gateway ? (var.single_nat_gateway ? 1 : length(var.private_subnet_cidrs)) : 0
  private_route_table_count = length(var.private_subnet_cidrs)
  eks_cluster_tags          = var.enable_eks_subnet_tags && var.eks_cluster_name != null ? { "kubernetes.io/cluster/${var.eks_cluster_name}" = "shared" } : {}
  public_subnet_tags = merge(
    local.common_tags,
    var.enable_eks_subnet_tags ? { "kubernetes.io/role/elb" = "1" } : {},
    local.eks_cluster_tags
  )
  private_subnet_tags = merge(
    local.common_tags,
    var.enable_eks_subnet_tags ? { "kubernetes.io/role/internal-elb" = "1" } : {},
    local.eks_cluster_tags
  )
}

resource "aws_vpc" "this" {
  cidr_block           = var.cidr_block
  enable_dns_support   = var.enable_dns_support
  enable_dns_hostnames = var.enable_dns_hostnames

  tags = merge(local.common_tags, {
    Name = local.name
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name}-igw"
  })
}

resource "aws_subnet" "public" {
  count = length(var.public_subnet_cidrs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = var.map_public_ip_on_launch

  tags = merge(local.public_subnet_tags, {
    Name = format("%s-public-%s", local.name, count.index + 1)
    Tier = "public"
  })
}

resource "aws_subnet" "private" {
  count = length(var.private_subnet_cidrs)

  vpc_id            = aws_vpc.this.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(local.private_subnet_tags, {
    Name = format("%s-private-%s", local.name, count.index + 1)
    Tier = "private"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name}-public"
  })
}

resource "aws_route" "public_internet_access" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = length(var.public_subnet_cidrs)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count = local.nat_gateway_count

  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = format("%s-nat-eip-%s", local.name, count.index + 1)
  })
}

resource "aws_nat_gateway" "this" {
  count = local.nat_gateway_count

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[var.single_nat_gateway ? 0 : count.index].id

  tags = merge(local.common_tags, {
    Name = format("%s-nat-%s", local.name, count.index + 1)
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "private" {
  count = local.private_route_table_count

  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = format("%s-private-%s", local.name, count.index + 1)
  })
}

resource "aws_route" "private_nat" {
  count = var.enable_nat_gateway && var.manage_private_nat_gateway_routes ? local.private_route_table_count : 0

  route_table_id         = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[var.single_nat_gateway ? 0 : count.index].id
}

resource "aws_route_table_association" "private" {
  count = length(var.private_subnet_cidrs)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
