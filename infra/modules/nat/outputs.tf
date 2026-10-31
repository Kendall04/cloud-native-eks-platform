output "launch_template_id" { value = aws_launch_template.nat.id }
output "launch_template_version" { value = aws_launch_template.nat.latest_version }
output "ami_id" { value = data.aws_ami.al2023.id }
output "user_data_sha256" { value = sha256(local.bootstrap) }
output "instance_profile_arn" { value = var.enable_ssm ? aws_iam_instance_profile.ssm[0].arn : null }
output "eip_allocation_id" { value = aws_eip.nat.id }

output "public_ip" {
  value = aws_eip.nat.public_ip
}

output "security_group_id" {
  value = aws_security_group.nat.id
}
