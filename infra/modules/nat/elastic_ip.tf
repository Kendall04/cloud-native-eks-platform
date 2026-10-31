resource "aws_eip" "nat" {
  domain = "vpc"
  tags = merge(var.tags, {
    "Name" = "${var.name_prefix}-nat-eip"
  })
}

# nat-egress recovery owns associations to dynamic ASG ENIs, not Terraform.
