data "aws_ami" "al2023" {
  most_recent = var.ami_id == null
  owners      = ["amazon"]

  filter {
    name   = var.ami_id == null ? "name" : "image-id"
    values = var.ami_id == null ? ["al2023-ami-2023*-kernel-6.1-x86_64"] : [var.ami_id]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}
