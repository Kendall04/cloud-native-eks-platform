mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "999988887777" }
  }
}
variables {
  iam_permissions_boundary_arn = "arn:aws:iam::999988887777:policy/test-private-cd-boundary"
  name                         = "test-cd"
  region                       = "us-east-1"
  artifact_bucket_name         = "test-artifacts-versioned"
  management_instance_id       = "i-0123456789abcdef0"
  management_role_name         = "test-management"
  repository_arns              = ["arn:aws:ecr:us-east-1:999988887777:repository/auth-service", "arn:aws:ecr:us-east-1:999988887777:repository/shipment-service", "arn:aws:ecr:us-east-1:999988887777:repository/tracking-service"]
  github_oidc_provider_arn     = "arn:aws:iam::999988887777:oidc-provider/token.actions.githubusercontent.com"
}
run "restricted_contract" {
  command = plan
  assert {
    condition     = alltrue([for role in aws_iam_role.federated : role.permissions_boundary == var.iam_permissions_boundary_arn])
    error_message = "Both delivery identities must retain the approved permissions boundary."
  }
  assert {
    condition     = jsondecode(aws_iam_role.federated["deployer"].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == ["repo:Kendall04/cloud-native-eks-platform:environment:dev"]
    error_message = "Deployment must use the exact dev environment subject."
  }
  assert {
    condition     = jsondecode(aws_iam_role.federated["publisher"].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    error_message = "Wrong OIDC audience."
  }
  assert {
    condition     = toset(keys(jsondecode(aws_ssm_document.deploy.content).parameters)) == toset(["ArtifactKey", "ArtifactVersionId", "ArtifactSha256", "DeploymentId", "ExpectedPreviousRevision"])
    error_message = "Only the five data parameters are allowed."
  }
  assert {
    condition     = alltrue([for p in values(jsondecode(aws_ssm_document.deploy.content).parameters) : p.interpolationType == "ENV_VAR" && startswith(p.allowedPattern, "^") && endswith(p.allowedPattern, "$")])
    error_message = "Every SSM parameter needs environment interpolation and a closed regex."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.publisher.policy).Statement[2].Condition.StringEquals["s3:if-none-match"] == "*"
    error_message = "Publication must be conditional."
  }
  assert {
    condition     = !strcontains(aws_iam_role_policy.publisher.policy, "ssm:") && !strcontains(aws_iam_role_policy.publisher.policy, "eks:")
    error_message = "Publisher cannot operate deployments."
  }
}
