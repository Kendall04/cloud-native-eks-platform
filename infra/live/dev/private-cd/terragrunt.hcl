include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}
terraform { source = "../../../modules/private-cd" }
locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}
dependency "management" { config_path = "../management" }
dependency "s3" { config_path = "../s3" }
dependency "ecr" { config_path = "../ecr" }
inputs = {
  github_oidc_provider_arn     = "arn:aws:iam::${get_aws_account_id()}:oidc-provider/token.actions.githubusercontent.com"
  iam_permissions_boundary_arn = "arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-private-cd-workload-boundary"
  name                         = "${local.env.locals.project_name}-${local.env.locals.environment}"
  github_repository            = "Kendall04/cloud-native-eks-platform"
  management_instance_id       = dependency.management.outputs.instance_id
  management_role_name         = dependency.management.outputs.iam_role_name
  artifact_bucket_name         = dependency.s3.outputs.bucket_ids.artifacts
  repository_arns              = values(dependency.ecr.outputs.repository_arns)
}
