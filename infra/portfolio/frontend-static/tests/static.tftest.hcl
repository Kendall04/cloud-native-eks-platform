# No credentials or AWS calls: all resources use Terraform's mocked provider.
mock_provider "aws" {
  mock_resource "aws_cloudfront_function" {
    defaults = { arn = "arn:aws:cloudfront::341936017254:function/offline-fixture" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::cloud-native-platform-341936017254-portfolio-demo", bucket_regional_domain_name = "cloud-native-platform-341936017254-portfolio-demo.s3.us-east-1.amazonaws.com" }
  }
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "341936017254"
      arn        = "arn:aws:sts::341936017254:assumed-role/fixture-hosting-owner/offline-test"
    }
  }
}
variables {
  execution_principal_arn = "arn:aws:sts::341936017254:assumed-role/fixture-hosting-owner/offline-test"
}
run "private_disabled_demo" {
  command = plan
  variables { release_sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  assert {
    condition     = !aws_cloudfront_distribution.site.enabled && !aws_s3_bucket.site.force_destroy
    error_message = "Initial host must be disabled and refuse force-purge."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.site.block_public_acls && aws_s3_bucket_public_access_block.site.ignore_public_acls && aws_s3_bucket_public_access_block.site.block_public_policy && aws_s3_bucket_public_access_block.site.restrict_public_buckets
    error_message = "Origin must remain private."
  }
  assert {
    condition     = aws_cloudfront_origin_access_control.site.signing_behavior == "always" && aws_cloudfront_origin_access_control.site.signing_protocol == "sigv4"
    error_message = "Origin requests must be signed/HTTPS."
  }
  assert {
    condition     = length(aws_cloudfront_distribution.site.origin) == 1 && aws_cloudfront_distribution.site.viewer_certificate[0].cloudfront_default_certificate && aws_cloudfront_distribution.site.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "Use one static origin and HTTPS viewer access without domain/secret."
  }
  assert {
    condition     = aws_cloudfront_distribution.site.default_cache_behavior[0].forwarded_values[0].cookies[0].forward == "none" && !aws_cloudfront_distribution.site.default_cache_behavior[0].forwarded_values[0].query_string && aws_cloudfront_distribution.site.default_cache_behavior[0].min_ttl == 0
    error_message = "Static cache must not forward sessions or force caching HTML."
  }
  assert {
    condition     = length(aws_cloudfront_distribution.site.default_cache_behavior[0].function_association) == 1 && strcontains(aws_cloudfront_function.routes.code, "API unavailable")
    error_message = "API and origin-write fail-closed routing is mandatory."
  }
}
run "select_verified_demo" {
  command = plan
  variables {
    release_sha256       = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    distribution_enabled = true
  }
  assert {
    condition     = aws_cloudfront_distribution.site.enabled && strcontains(aws_cloudfront_function.routes.code, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    error_message = "A selection must bind the exact release."
  }
}
run "reject_bad_hash" {
  command = plan
  variables { release_sha256 = "not-a-reviewed-release" }
  expect_failures = [var.release_sha256]
}

run "reject_wrong_owner" {
  command = plan
  variables {
    release_sha256          = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    execution_principal_arn = "arn:aws:sts::341936017254:assumed-role/other-hosting-owner/offline-test"
  }
  expect_failures = [aws_s3_bucket.site]
}
run "existing_api_integration" {
  # Mocked apply resolves computed IDs inside the two-origin set. No AWS client.
  command = apply
  variables {
    release_sha256  = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    site_mode       = "aws"
    api_enabled     = true
    api_domain_name = "abc123def4.execute-api.us-east-1.amazonaws.com"
  }
  assert {
    condition     = length(aws_cloudfront_distribution.site.origin) == 2 && length(aws_cloudfront_distribution.site.ordered_cache_behavior) == 2
    error_message = "API is an existing second origin with separate /api behaviors."
  }
  assert {
    condition     = alltrue([for b in aws_cloudfront_distribution.site.ordered_cache_behavior : b.cache_policy_id == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" && b.origin_request_policy_id == "b689b0a8-53d0-40ab-baf2-68738e2966ac"])
    error_message = "API cache disabled; bearer forwarded without viewer Host."
  }
  assert {
    condition     = alltrue([for e in aws_cloudfront_distribution.site.custom_error_response : e.error_caching_min_ttl == 0 && (e.response_code == null || e.response_code == 0) && (e.response_page_path == null || e.response_page_path == "")])
    error_message = "API errors may never become cached SPA/custom pages."
  }
}
run "reject_demo_with_api" {
  command = plan
  variables {
    release_sha256  = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    api_enabled     = true
    api_domain_name = "abc123def4.execute-api.us-east-1.amazonaws.com"
  }
  expect_failures = [aws_s3_bucket.site]
}
run "reject_external_api" {
  command = plan
  variables {
    release_sha256  = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    site_mode       = "aws"
    api_enabled     = true
    api_domain_name = "external.example.invalid"
  }
  expect_failures = [aws_s3_bucket.site]
}
