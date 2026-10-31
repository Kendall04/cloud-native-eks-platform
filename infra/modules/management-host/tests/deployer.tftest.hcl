mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "999988887777" }
  }
}
variables {
  project_name                   = "test-platform"
  environment                    = "dev"
  region                         = "us-east-1"
  name                           = "test-management"
  vpc_id                         = "vpc-0123456789abcdef0"
  vpc_cidr_block                 = "10.20.0.0/16"
  private_subnet_id              = "subnet-0123456789abcdef0"
  rds_subnet_cidrs               = ["10.0.128.0/20", "10.0.144.0/20", "10.0.160.0/20"]
  cluster_name                   = "test-platform-dev"
  cluster_security_group_id      = "sg-0123456789abcdef0"
  alb_frontend_security_group_id = "sg-abcdef01234567890"
  artifact_bucket_name           = "test-artifacts"
  api_endpoint                   = "https://test.execute-api.us-east-1.amazonaws.com"
}
run "private_fixed_deployer" {
  command = plan
  assert {
    condition     = toset(keys(local.deployer_files)) == toset(["contract.py", "diagnostics.py", "engine.py", "executor.py", "manifest.schema.json", "chart-template-hashes.json"])
    error_message = "The default host must keep the admitted dev runtime; synthetic capability stays source-only."
  }
  assert {
    condition = alltrue([for cidr, rule in aws_vpc_security_group_egress_rule.rds_postgresql :
      rule.cidr_ipv4 == cidr && rule.from_port == 5432 && rule.to_port == 5432 && rule.ip_protocol == "tcp"
    ]) && length(aws_vpc_security_group_egress_rule.rds_postgresql) == 3
    error_message = "PostgreSQL egress must remain limited to the three reviewed private subnets."
  }
  assert {
    condition     = length(aws_instance.management.user_data_base64) <= 21848
    error_message = "Compressed user data must fit EC2's 16 KiB limit before base64 encoding."
  }
  assert {
    condition     = aws_instance.management.associate_public_ip_address == false && aws_instance.management.metadata_options[0].http_tokens == "required"
    error_message = "Management must stay private with IMDSv2."
  }
  assert {
    condition     = aws_eks_access_entry.management.kubernetes_groups == toset(["platform:deployer:apps"])
    error_message = "Management must retain the R3 namespace group."
  }
}
