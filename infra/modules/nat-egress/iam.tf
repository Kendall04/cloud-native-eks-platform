resource "aws_iam_role" "recovery" {
  count              = local.recovery_count
  name               = local.recovery_name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags               = var.tags
}

resource "aws_iam_role_policy" "recovery" {
  count = local.recovery_count
  name  = "fixed-slot-recovery"
  role  = aws_iam_role.recovery[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Sid = "DescribeMembership", Effect = "Allow", Resource = "*", Action = [
      "autoscaling:DescribeAutoScalingGroups", "ec2:DescribeInstances", "ec2:DescribeInstanceStatus",
      "ec2:DescribeNetworkInterfaces", "ec2:DescribeLaunchTemplateVersions",
      "ec2:DescribeAddresses", "ec2:DescribeRouteTables"
    ], Condition = { StringEquals = { "aws:RequestedRegion" = var.region } } },
    { Sid      = "BootstrapReadback", Effect = "Allow", Action = ["ec2:GetConsoleOutput", "ec2:DescribeInstanceAttribute"],
      Resource = "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*",
    Condition = { StringEquals = { "aws:ResourceTag/Project" = var.project_name, "aws:ResourceTag/Environment" = var.environment, "aws:ResourceTag/Role" = "nat", "aws:ResourceTag/NatSlot" = [for slot in local.recovery_config.slots : slot.az] } } },
    { Sid      = "OnlySourceDestCheck", Effect = "Allow", Action = "ec2:ModifyInstanceAttribute",
      Resource = "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*",
    Condition = { StringEquals = { "ec2:Attribute" = "SourceDestCheck", "aws:ResourceTag/Project" = var.project_name, "aws:ResourceTag/Environment" = var.environment, "aws:ResourceTag/Role" = "nat", "aws:ResourceTag/NatSlot" = [for slot in local.recovery_config.slots : slot.az] } } },
    { Sid = "ExactEipAllocations", Effect = "Allow", Action = "ec2:AssociateAddress",
    Resource = [for slot in local.recovery_config.slots : "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:elastic-ip/${slot.eip}"] },
    { Sid      = "ProtectedEnis", Effect = "Allow", Action = "ec2:AssociateAddress",
      Resource = "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:network-interface/*",
    Condition = { StringEquals = { "ec2:Subnet" = [for slot in local.recovery_config.slots : "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:subnet/${slot.subnet}"], "aws:ResourceTag/Project" = var.project_name, "aws:ResourceTag/Environment" = var.environment, "aws:ResourceTag/Role" = "nat" } } },
    { Sid = "ExactPrivateRouteTables", Effect = "Allow", Action = ["ec2:CreateRoute", "ec2:ReplaceRoute"],
    Resource = [for slot in local.recovery_config.slots : "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:route-table/${slot.table}"] },
    { Sid = "ReadControlAndSlots", Effect = "Allow", Action = "dynamodb:GetItem", Resource = aws_dynamodb_table.recovery[0].arn,
    Condition = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = concat(["CONTROL"], [for slot in local.recovery_config.slots : "SLOT#${slot.asg}"]) } } },
    { Sid = "WriteSlotsNeverControl", Effect = "Allow", Action = "dynamodb:PutItem", Resource = aws_dynamodb_table.recovery[0].arn,
    Condition = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = [for slot in local.recovery_config.slots : "SLOT#${slot.asg}"] } } },
    { Sid = "OwnLogStreams", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.recovery[0].arn}:*" },
    { Sid = "RetainAsyncFailure", Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.failures[0].arn }
  ] })
}
