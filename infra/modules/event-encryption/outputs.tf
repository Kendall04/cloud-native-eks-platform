output "key_arn" { value = aws_kms_key.events.arn }
output "key_id" { value = aws_kms_key.events.key_id }
output "alias" { value = aws_kms_alias.events.name }
output "rotation_enabled" { value = aws_kms_key.events.enable_key_rotation }
output "deletion_window_in_days" { value = aws_kms_key.events.deletion_window_in_days }
