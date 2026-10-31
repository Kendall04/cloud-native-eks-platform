output "publisher_role_arn" { value = aws_iam_role.federated["publisher"].arn }
output "deployment_role_arn" { value = aws_iam_role.federated["deployer"].arn }
output "document_name" { value = aws_ssm_document.deploy.name }
output "document_version" { value = aws_ssm_document.deploy.latest_version }
output "document_sha256" { value = aws_ssm_document.deploy.hash }
output "artifact_bucket_name" { value = var.artifact_bucket_name }
output "management_instance_id" { value = var.management_instance_id }
