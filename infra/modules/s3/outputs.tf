output "bucket_arns" {
  description = "ARNs of the created S3 buckets."
  value       = { for name, bucket in aws_s3_bucket.this : name => bucket.arn }
}

output "bucket_domain_names" {
  description = "Domain names of the created S3 buckets."
  value       = { for name, bucket in aws_s3_bucket.this : name => bucket.bucket_domain_name }
}

output "bucket_ids" {
  description = "IDs of the created S3 buckets."
  value       = { for name, bucket in aws_s3_bucket.this : name => bucket.id }
}

