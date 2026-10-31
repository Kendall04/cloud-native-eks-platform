terraform {
  required_version = "= 1.13.4"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 5.100.0" }
  }
  # Independent local state. Future operator must place state/plans in a private
  # directory outside this checkout; never join the EKS eighteen-state backend.
}
provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = ["341936017254"]
}
variable "execution_principal_arn" {
  type     = string
  nullable = false
  validation {
    condition     = can(regex("^arn:aws:(iam|sts)::341936017254:(user/|role/|assumed-role/).+$", var.execution_principal_arn))
    error_message = "Bind the exact separately reviewed hosting-owner caller ARN; no default principal."
  }
}
data "aws_caller_identity" "owner" {}
variable "release_sha256" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.release_sha256))
    error_message = "Supply the verified DEMO package SHA256."
  }
}
variable "distribution_enabled" {
  type    = bool
  default = false
}
variable "site_mode" {
  type    = string
  default = "demo"
  validation {
    condition     = contains(["demo", "aws"], var.site_mode)
    error_message = "Select the verified package mode explicitly."
  }
}
variable "api_enabled" {
  type    = bool
  default = false
}
variable "api_domain_name" {
  type     = string
  default  = null
  nullable = true
}
locals {
  name   = "cnp-portfolio-demo"
  bucket = "cloud-native-platform-341936017254-portfolio-demo"
  tags   = { Project = "cloud-native-platform", Environment = "portfolio-demo", Owner = "Kendall", ManagedBy = "Terraform", Lifecycle = "SEPARATE_FROM_EKS" }
}
resource "aws_s3_bucket" "site" {
  bucket        = local.bucket
  force_destroy = false
  tags          = local.tags
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.owner.account_id == "341936017254" && data.aws_caller_identity.owner.arn == var.execution_principal_arn
      error_message = "Hosting-owner identity differs from the exact reviewed binding."
    }
    precondition {
      condition     = var.api_enabled ? (var.site_mode == "aws" && can(regex("^[a-z0-9]{10}\\.execute-api\\.us-east-1\\.amazonaws\\.com$", var.api_domain_name))) : var.api_domain_name == null
      error_message = "Live routing needs an AWS package and exact existing regional API hostname; offline has no API origin."
    }
  }
}
resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_cloudfront_origin_access_control" "site" {
  name                              = local.name
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}
resource "aws_cloudfront_function" "routes" {
  name    = "${local.name}-routes"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = templatefile("${path.module}/routes.js.tftpl", { release_sha256 = var.release_sha256 })
}
resource "aws_cloudfront_function" "api" {
  count   = var.api_enabled ? 1 : 0
  name    = "${local.name}-api"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/api-routes.js")
}
resource "aws_cloudfront_response_headers_policy" "api" {
  count = var.api_enabled ? 1 : 0
  name  = "${local.name}-api-no-store"
  custom_headers_config {
    items {
      header   = "Cache-Control"
      value    = "no-store"
      override = true
    }
  }
  security_headers_config {
    content_type_options { override = true }
  }
}
resource "aws_cloudfront_response_headers_policy" "site" {
  name = "${local.name}-headers"
  security_headers_config {
    content_type_options { override = true }
    frame_options {
      frame_option = "SAMEORIGIN"
      override     = true
    }
    referrer_policy {
      referrer_policy = "no-referrer"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      override                   = true
    }
    content_security_policy {
      # Explorer fetches pinned same-origin JSON and renders pinned inline srcdoc.
      # No API/external connect origins; child documents also have their own CSP.
      content_security_policy = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self' about: blob:; frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'none'"
      override                = true
    }
  }
}
resource "aws_cloudfront_distribution" "site" {
  enabled             = var.distribution_enabled
  comment             = "${var.site_mode} package; API routing ${var.api_enabled ? "enabled" : "offline"}"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  is_ipv6_enabled     = true
  wait_for_deployment = true
  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "private-static"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }
  dynamic "origin" {
    for_each = var.api_enabled ? [var.api_domain_name] : []
    content {
      domain_name = origin.value
      origin_id   = "existing-http-api"
      # Existing HTTP API uses $default: no stage or /api origin_path.
      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }
  }
  dynamic "ordered_cache_behavior" {
    for_each = var.api_enabled ? ["/api", "/api/*"] : []
    content {
      path_pattern               = ordered_cache_behavior.value
      target_origin_id           = "existing-http-api"
      viewer_protocol_policy     = "redirect-to-https"
      allowed_methods            = ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"]
      cached_methods             = ["GET", "HEAD"]
      cache_policy_id            = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # AWS CachingDisabled, TTLs all zero.
      origin_request_policy_id   = "b689b0a8-53d0-40ab-baf2-68738e2966ac" # AllViewerExceptHostHeader.
      response_headers_policy_id = aws_cloudfront_response_headers_policy.api[0].id
      function_association {
        event_type   = "viewer-request"
        function_arn = aws_cloudfront_function.api[0].arn
      }
    }
  }
  default_cache_behavior {
    target_origin_id       = "private-static"
    viewer_protocol_policy = "redirect-to-https"
    # Viewer function rejects all origin writes; bucket grant is GetObject only.
    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"]
    cached_methods  = ["GET", "HEAD"]
    compress        = true
    min_ttl         = 0
    default_ttl     = 3600
    max_ttl         = 31536000
    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
    response_headers_policy_id = aws_cloudfront_response_headers_policy.site.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.routes.arn
    }
  }
  # Preserve origin errors. ResponseCode requires a custom ResponsePagePath in
  # AWS; neither is needed here, and no error may become SPA HTML.
  custom_error_response {
    error_code            = 403
    error_caching_min_ttl = 0
  }
  dynamic "custom_error_response" {
    for_each = var.api_enabled ? toset([400, 404, 405, 414, 416, 500, 501, 502, 503, 504]) : toset([])
    content {
      error_code            = custom_error_response.value
      error_caching_min_ttl = 0
    }
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate {
    # AWS forces its TLSv1 security policy for the default cloudfront.net name.
    # No false TLS1.2-floor claim; explicit static-only limitation in approval JSON.
    cloudfront_default_certificate = true
  }
  tags = local.tags
}
resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid      = "OnlyExactDistributionRead", Effect = "Allow", Principal = { Service = "cloudfront.amazonaws.com" }, Action = "s3:GetObject",
        Resource = ["${aws_s3_bucket.site.arn}/releases/*", "${aws_s3_bucket.site.arn}/assets/*", "${aws_s3_bucket.site.arn}/architecture-assets/*"],
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.site.arn } } },
      { Sid = "DenyPlainHttp", Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.site.arn, "${aws_s3_bucket.site.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }
    ]
  })
}
output "hosting_identity" {
  value = { bucket = aws_s3_bucket.site.id, distribution_id = aws_cloudfront_distribution.site.id, distribution_arn = aws_cloudfront_distribution.site.arn, domain_name = aws_cloudfront_distribution.site.domain_name, routes_arn = aws_cloudfront_function.routes.arn, active_release_sha256 = var.release_sha256, mode = var.site_mode, api_enabled = var.api_enabled }
}
