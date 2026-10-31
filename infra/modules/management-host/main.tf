locals {
  name            = var.name
  artifact_prefix = trim(var.artifact_prefix, "/")

  # The default host remains the admitted dev capability. Synthetic capability
  # files remain source-only until a separately reviewed installation exists.
  deployer_files = { for name in setsubtract(setunion(fileset("${path.module}/deployer", "*.py"), fileset("${path.module}/deployer", "*.json")), toset([
    "synthetic_contract.py", "environment.synthetic.schema.json", "manifest.synthetic.schema.json", "synthetic-protected-resources.json"
  ])) : name => file("${path.module}/deployer/${name}") }

  common_tags = merge(var.tags, {
    Name   = local.name
    Module = "management-host"
    Role   = "management"
  })
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_caller_identity" "current" {}

resource "aws_security_group" "management" {
  name        = "${local.name}-sg"
  description = "Private SSM management host with EKS API egress."
  vpc_id      = var.vpc_id

  tags = merge(local.common_tags, {
    Name = "${local.name}-sg"
  })
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.management.id
  description       = "HTTPS egress for SSM, AWS APIs, package downloads, and EKS API."
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "dns_tcp" {
  security_group_id = aws_security_group.management.id
  description       = "TCP DNS egress to VPC resolver."
  ip_protocol       = "tcp"
  from_port         = 53
  to_port           = 53
  cidr_ipv4         = var.vpc_cidr_block
}

# RDS uses these VPC-owned subnets. Do not depend on RDS outputs: its state
# is already empty when management is destroyed during approved teardown.
resource "aws_vpc_security_group_egress_rule" "rds_postgresql" {
  for_each = var.rds_subnet_cidrs

  security_group_id = aws_security_group.management.id
  description       = "PostgreSQL TLS transit to reviewed private RDS subnets."
  ip_protocol       = "tcp"
  from_port         = 5432
  to_port           = 5432
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_egress_rule" "dns_udp" {
  security_group_id = aws_security_group.management.id
  description       = "UDP DNS egress to VPC resolver."
  ip_protocol       = "udp"
  from_port         = 53
  to_port           = 53
  cidr_ipv4         = var.vpc_cidr_block
}

resource "aws_vpc_security_group_egress_rule" "internal_alb_http" {
  for_each = var.internal_alb_http_egress_security_group_ids

  security_group_id            = aws_security_group.management.id
  referenced_security_group_id = each.value
  description                  = "HTTP egress to internal ALB for private platform smoke tests."
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_vpc_security_group_ingress_rule" "eks_api_from_management" {
  security_group_id            = var.cluster_security_group_id
  referenced_security_group_id = aws_security_group.management.id
  description                  = "Allow private management host to reach the EKS API server."
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}

resource "aws_iam_role" "management" {
  permissions_boundary = var.iam_permissions_boundary_arn
  name                 = "${local.name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name}-role"
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.management.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "eks_read_only" {
  name = "${local.name}-eks-read-only"
  role = aws_iam_role.management.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DescribeTargetCluster"
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster"
        ]
        Resource = "arn:aws:eks:${var.region}:${data.aws_caller_identity.current.account_id}:cluster/${var.cluster_name}"
      }
    ]
  })
}

resource "aws_iam_role_policy" "artifact_read_only" {
  count = var.artifact_bucket_name == null ? 0 : 1

  name = "${local.name}-artifact-read-only"
  role = aws_iam_role.management.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ListArtifactPrefix"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = "arn:aws:s3:::${var.artifact_bucket_name}"
        Condition = {
          StringLike = {
            "s3:prefix" = [
              local.artifact_prefix,
              "${local.artifact_prefix}/*"
            ]
          }
        }
      },
      {
        Sid    = "ReadArtifactObjects"
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = "arn:aws:s3:::${var.artifact_bucket_name}/${local.artifact_prefix}/*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "management" {
  name = "${local.name}-profile"
  role = aws_iam_role.management.name

  tags = merge(local.common_tags, {
    Name = "${local.name}-profile"
  })
}

resource "aws_eks_access_entry" "management" {
  cluster_name      = var.cluster_name
  principal_arn     = aws_iam_role.management.arn
  type              = "STANDARD"
  kubernetes_groups = ["platform:deployer:apps"]

  tags = merge(local.common_tags, {
    Name = "${local.name}-eks-access"
  })
}

resource "aws_instance" "management" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = var.instance_type
  subnet_id                   = var.private_subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.management.name
  vpc_security_group_ids      = [aws_security_group.management.id]
  user_data_replace_on_change = true

  # Bootstrap is creation-only. Reviewed deployer updates are installed under
  # the host deployment lock; changing embedded files must not replace this host.
  lifecycle {
    ignore_changes = [user_data_base64]
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    encrypted   = true
    volume_size = var.root_volume_size
    volume_type = "gp3"
  }

  user_data_base64 = base64gzip(templatefile("${path.module}/user_data.sh.tftpl", {
    kubectl_version = var.kubectl_version
    helm_version    = var.helm_version
    deployer_bundle = base64gzip(jsonencode(local.deployer_files))
    deployer_config = base64encode(jsonencode({
      environment = var.environment
      accountId   = data.aws_caller_identity.current.account_id
      region      = var.region
      clusterName = var.cluster_name
      namespace   = "apps"
      helmRelease = "platform-services"
      alb = {
        groupName               = var.project_name
        frontendSecurityGroupId = var.alb_frontend_security_group_id
        discoveryTags           = { Project = var.project_name, Environment = var.environment }
      }
      shipmentQueueUrl = "https://sqs.${var.region}.amazonaws.com/${data.aws_caller_identity.current.account_id}/${var.project_name}-${var.environment}-shipment-events-queue"
      bucket           = var.artifact_bucket_name
      apiEndpoint      = var.api_endpoint
      repositories     = { for name in ["auth", "shipment", "tracking"] : name => "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com/${name}-service" }
    }))
  }))

  tags = local.common_tags

  depends_on = [
    aws_iam_role_policy_attachment.ssm,
    aws_iam_role_policy.eks_read_only,
    aws_iam_role_policy.artifact_read_only
  ]
}
