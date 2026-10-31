locals {
  cluster_name = coalesce(var.cluster_name, "${var.project_name}-${var.environment}-eks")
  common_tags  = merge(var.tags, { Module = "eks" })

  managed_node_groups = {
    "api-node-group"    = var.api_node_group
    "worker-node-group" = var.worker_node_group
  }

  irsa_addons = {
    "vpc-cni" = {
      namespace       = "kube-system"
      service_account = "aws-node"
      policy_arn      = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEKS_CNI_Policy"
    }
    "aws-ebs-csi-driver" = {
      namespace       = "kube-system"
      service_account = "ebs-csi-controller-sa"
      policy_arn      = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
    }
  }

  enabled_addons = toset(var.enabled_addons)
  bootstrap_addons = toset([
    for addon_name in var.enabled_addons : addon_name
    if addon_name == "vpc-cni"
  ])
  post_compute_addons = toset([
    for addon_name in var.enabled_addons : addon_name
    if addon_name != "vpc-cni"
  ])
  enabled_irsa_addons = {
    for addon_name, addon in local.irsa_addons : addon_name => addon
    if contains(var.enabled_addons, addon_name)
  }

  aws_load_balancer_controller_subject = "system:serviceaccount:${var.aws_load_balancer_controller_namespace}:${var.aws_load_balancer_controller_service_account_name}"
  cluster_autoscaler_subject           = "system:serviceaccount:${var.cluster_autoscaler_namespace}:${var.cluster_autoscaler_service_account_name}"
}

data "aws_partition" "current" {}

data "aws_iam_policy_document" "cluster_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "node_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/eks/${local.cluster_name}/cluster"
  retention_in_days = var.cluster_log_retention_in_days

  tags = merge(local.common_tags, {
    Name = "/aws/eks/${local.cluster_name}/cluster"
  })
}

resource "aws_iam_role" "cluster" {
  permissions_boundary = var.iam_permissions_boundary_arn
  name                 = "${local.cluster_name}-cluster-role"
  assume_role_policy   = data.aws_iam_policy_document.cluster_assume_role.json

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-cluster-role"
  })
}

resource "aws_iam_role_policy_attachment" "cluster_policy" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role" "node" {
  permissions_boundary = var.iam_permissions_boundary_arn
  for_each             = local.managed_node_groups

  name               = "${local.cluster_name}-${each.key}-role"
  assume_role_policy = data.aws_iam_policy_document.node_assume_role.json

  tags = merge(local.common_tags, each.value.tags, {
    Name = "${local.cluster_name}-${each.key}-role"
  })
}

resource "aws_iam_role_policy_attachment" "node_worker_policy" {
  for_each = aws_iam_role.node

  role       = each.value.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_ecr_pull_policy" {
  for_each = aws_iam_role.node

  role       = each.value.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly"
}

resource "aws_eks_cluster" "this" {
  name     = local.cluster_name
  role_arn = aws_iam_role.cluster.arn
  version  = var.cluster_version

  enabled_cluster_log_types = var.enabled_cluster_log_types

  access_config {
    authentication_mode                         = var.cluster_access_mode
    bootstrap_cluster_creator_admin_permissions = var.bootstrap_cluster_creator_admin_permissions
  }

  vpc_config {
    subnet_ids              = var.private_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = false
  }

  tags = merge(local.common_tags, {
    Name = local.cluster_name
  })

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy_attachment.cluster_policy,
  ]
}

data "tls_certificate" "oidc" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "this" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.oidc.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

data "aws_iam_policy_document" "irsa_assume_role" {
  for_each = local.enabled_irsa_addons

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.this.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:${each.value.namespace}:${each.value.service_account}"]
    }
  }
}

resource "aws_iam_role" "irsa" {
  permissions_boundary = var.iam_permissions_boundary_arn
  for_each             = local.enabled_irsa_addons

  name               = "${local.cluster_name}-${each.key}-irsa-role"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume_role[each.key].json

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-${each.key}-irsa-role"
  })
}

resource "aws_iam_role_policy_attachment" "irsa_policy" {
  for_each = local.enabled_irsa_addons

  role       = aws_iam_role.irsa[each.key].name
  policy_arn = each.value.policy_arn
}

data "aws_iam_policy_document" "aws_load_balancer_controller_assume_role" {
  count = var.create_aws_load_balancer_controller_prerequisites ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.this.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:sub"
      values   = [local.aws_load_balancer_controller_subject]
    }
  }
}

resource "aws_iam_policy" "aws_load_balancer_controller" {
  count = var.create_aws_load_balancer_controller_prerequisites ? 1 : 0

  name        = "${local.cluster_name}-aws-load-balancer-controller"
  description = "IAM policy for the AWS Load Balancer Controller."
  policy      = file("${path.module}/policies/aws-load-balancer-controller-iam-policy.json")

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-aws-load-balancer-controller"
  })
}

resource "aws_iam_role" "aws_load_balancer_controller" {
  permissions_boundary = var.iam_permissions_boundary_arn
  count                = var.create_aws_load_balancer_controller_prerequisites ? 1 : 0

  name               = "${local.cluster_name}-aws-load-balancer-controller-role"
  assume_role_policy = data.aws_iam_policy_document.aws_load_balancer_controller_assume_role[0].json

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-aws-load-balancer-controller-role"
  })
}

resource "aws_iam_role_policy_attachment" "aws_load_balancer_controller" {
  count = var.create_aws_load_balancer_controller_prerequisites ? 1 : 0

  role       = aws_iam_role.aws_load_balancer_controller[0].name
  policy_arn = aws_iam_policy.aws_load_balancer_controller[0].arn
}

data "aws_iam_policy_document" "cluster_autoscaler_assume_role" {
  count = var.create_cluster_autoscaler_prerequisites ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.this.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.this.url, "https://", "")}:sub"
      values   = [local.cluster_autoscaler_subject]
    }
  }
}

data "aws_iam_policy_document" "cluster_autoscaler" {
  count = var.create_cluster_autoscaler_prerequisites ? 1 : 0

  statement {
    sid = "ClusterAutoscalerScaleNodeGroups"

    actions = [
      "autoscaling:SetDesiredCapacity",
      "autoscaling:TerminateInstanceInAutoScalingGroup",
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/k8s.io/cluster-autoscaler/enabled"
      values   = ["true"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/k8s.io/cluster-autoscaler/${local.cluster_name}"
      values   = ["owned"]
    }
  }

  statement {
    sid = "ClusterAutoscalerDescribeNodeGroups"

    actions = [
      "autoscaling:DescribeAutoScalingGroups",
      "autoscaling:DescribeAutoScalingInstances",
      "autoscaling:DescribeLaunchConfigurations",
      "autoscaling:DescribeScalingActivities",
      "autoscaling:DescribeTags",
      "ec2:DescribeImages",
      "ec2:DescribeInstanceTypes",
      "ec2:DescribeLaunchTemplateVersions",
      "ec2:GetInstanceTypesFromInstanceRequirements",
      "eks:DescribeNodegroup",
    ]

    resources = ["*"]
  }
}

resource "aws_iam_policy" "cluster_autoscaler" {
  count = var.create_cluster_autoscaler_prerequisites ? 1 : 0

  name        = "${local.cluster_name}-cluster-autoscaler"
  description = "Least-privilege IAM policy for Kubernetes Cluster Autoscaler."
  policy      = data.aws_iam_policy_document.cluster_autoscaler[0].json

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-cluster-autoscaler"
  })
}

resource "aws_iam_role" "cluster_autoscaler" {
  permissions_boundary = var.iam_permissions_boundary_arn
  count                = var.create_cluster_autoscaler_prerequisites ? 1 : 0

  name               = "${local.cluster_name}-cluster-autoscaler-role"
  assume_role_policy = data.aws_iam_policy_document.cluster_autoscaler_assume_role[0].json

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-cluster-autoscaler-role"
  })
}

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  count = var.create_cluster_autoscaler_prerequisites ? 1 : 0

  role       = aws_iam_role.cluster_autoscaler[0].name
  policy_arn = aws_iam_policy.cluster_autoscaler[0].arn
}

data "aws_eks_addon_version" "this" {
  for_each = local.enabled_addons

  addon_name         = each.value
  kubernetes_version = var.cluster_version
  most_recent        = true
}

resource "aws_eks_addon" "bootstrap" {
  for_each = local.bootstrap_addons

  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = each.value
  addon_version               = lookup(var.addon_versions, each.value, data.aws_eks_addon_version.this[each.value].version)
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  service_account_role_arn    = try(aws_iam_role.irsa[each.value].arn, null)
  configuration_values = each.value == "vpc-cni" ? jsonencode({
    enableNetworkPolicy = "true"
    env                 = { NETWORK_POLICY_ENFORCING_MODE = "standard" }
  }) : null

  depends_on = [
    aws_iam_role_policy_attachment.irsa_policy,
  ]
}

resource "aws_launch_template" "encrypted" {
  for_each = local.managed_node_groups

  name_prefix = "${local.cluster_name}-${each.key}-encrypted-"
  description = "EKS managed bootstrap with encrypted gp3 root storage."

  # EKS supplies the optimized AL2023 AMI, node IAM profile, cluster SG and
  # bootstrap. Do not duplicate those fields in the custom template.
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      encrypted             = true
      volume_type           = "gp3"
      volume_size           = each.value.disk_size
      delete_on_termination = true
    }
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.common_tags, each.value.tags, { Name = "${local.cluster_name}-${each.key}-encrypted" })
  }
  tag_specifications {
    resource_type = "volume"
    tags          = merge(local.common_tags, { Name = "${local.cluster_name}-${each.key}-encrypted-root" })
  }
  tags = merge(local.common_tags, { Name = "${local.cluster_name}-${each.key}-encrypted" })
  lifecycle { create_before_destroy = true }
}

resource "aws_eks_node_group" "encrypted" {
  for_each = local.managed_node_groups

  cluster_name           = aws_eks_cluster.this.name
  node_group_name_prefix = "${each.key}-encrypted-"
  node_role_arn          = aws_iam_role.node[each.key].arn
  subnet_ids             = var.private_subnet_ids
  version                = var.cluster_version
  release_version        = var.node_ami_release_version
  ami_type               = each.value.ami_type
  capacity_type          = each.value.capacity_type
  instance_types         = each.value.instance_types
  labels                 = each.value.labels
  launch_template {
    id      = aws_launch_template.encrypted[each.key].id
    version = tostring(aws_launch_template.encrypted[each.key].latest_version)
  }
  scaling_config {
    desired_size = each.value.desired_size
    max_size     = each.value.max_size
    min_size     = each.value.min_size
  }
  update_config { max_unavailable = 1 }
  lifecycle {
    create_before_destroy = true
    ignore_changes        = [scaling_config[0].desired_size]
  }
  tags = merge(local.common_tags, each.value.tags, { Name = "${local.cluster_name}-${each.key}-encrypted" })
  depends_on = [
    aws_eks_addon.bootstrap,
    aws_iam_role_policy_attachment.node_worker_policy,
    aws_iam_role_policy_attachment.node_ecr_pull_policy,
  ]
}

resource "aws_eks_addon" "post_compute" {
  for_each = local.post_compute_addons

  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = each.value
  addon_version               = lookup(var.addon_versions, each.value, data.aws_eks_addon_version.this[each.value].version)
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  service_account_role_arn    = try(aws_iam_role.irsa[each.value].arn, null)

  depends_on = [
    aws_eks_node_group.encrypted,
    aws_iam_role_policy_attachment.irsa_policy,
  ]
}
