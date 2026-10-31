#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="${PROJECT_NAME:-cloud-native-platform}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

if [[ -z "${AWS_REGION}" ]]; then
  echo "AWS_REGION must not be empty." >&2
  exit 1
fi

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command not found: ${command_name}" >&2
    exit 1
  fi
}

aws_cmd() {
  aws --region "${AWS_REGION}" "$@"
}

require_command aws

if [[ -z "${AWS_ACCOUNT_ID:-}" ]]; then
  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
fi

CALLER_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text)"

if [[ "${CALLER_ACCOUNT_ID}" != "${AWS_ACCOUNT_ID}" ]]; then
  echo "AWS_ACCOUNT_ID (${AWS_ACCOUNT_ID}) does not match caller account (${CALLER_ACCOUNT_ID})." >&2
  exit 1
fi

STATE_BUCKET="${PROJECT_NAME}-${AWS_ACCOUNT_ID}-${ENVIRONMENT}-${AWS_REGION}-tfstate"
LOCK_TABLE="${PROJECT_NAME}-${AWS_ACCOUNT_ID}-${ENVIRONMENT}-terraform-locks"

validate_region() {
  if ! aws ec2 describe-regions \
    --region "${AWS_REGION}" \
    --region-names "${AWS_REGION}" \
    --query "Regions[0].RegionName" \
    --output text >/dev/null 2>&1; then
    echo "AWS region is not available or not accessible: ${AWS_REGION}" >&2
    exit 1
  fi
}

bucket_owned_by_caller_account() {
  aws s3api list-buckets \
    --query "contains(Buckets[].Name, '${STATE_BUCKET}')" \
    --output text
}

ensure_bucket() {
  local head_output

  if head_output="$(aws s3api head-bucket --bucket "${STATE_BUCKET}" 2>&1)"; then
    if [[ "$(bucket_owned_by_caller_account)" != "True" ]]; then
      echo "Bucket ${STATE_BUCKET} is accessible but was not returned by list-buckets for this account." >&2
      echo "Refusing to modify a bucket that may belong to another account." >&2
      exit 1
    fi

    echo "S3 state bucket already exists and is owned by this account: ${STATE_BUCKET}"
    return
  fi

  if grep -q "Forbidden" <<<"${head_output}"; then
    echo "Bucket ${STATE_BUCKET} exists but is not accessible to this account." >&2
    echo "Choose a different bucket name or fix ownership/policy before bootstrapping." >&2
    exit 1
  fi

  if ! grep -Eq "Not Found|NotFound|404|NoSuchBucket" <<<"${head_output}"; then
    echo "Unable to determine bucket status for ${STATE_BUCKET}:" >&2
    echo "${head_output}" >&2
    exit 1
  fi

  echo "Creating S3 state bucket: ${STATE_BUCKET}"
  if [[ "${AWS_REGION}" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "${STATE_BUCKET}" >/dev/null
  else
    aws s3api create-bucket \
      --bucket "${STATE_BUCKET}" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}" >/dev/null
  fi

  aws s3api wait bucket-exists --bucket "${STATE_BUCKET}"
}

configure_bucket() {
  echo "Configuring S3 state bucket security controls."

  aws s3api put-bucket-versioning \
    --bucket "${STATE_BUCKET}" \
    --versioning-configuration Status=Enabled

  aws s3api put-bucket-encryption \
    --bucket "${STATE_BUCKET}" \
    --server-side-encryption-configuration '{
      "Rules": [
        {
          "ApplyServerSideEncryptionByDefault": {
            "SSEAlgorithm": "AES256"
          }
        }
      ]
    }'

  aws s3api put-public-access-block \
    --bucket "${STATE_BUCKET}" \
    --public-access-block-configuration \
      BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

  aws s3api put-bucket-ownership-controls \
    --bucket "${STATE_BUCKET}" \
    --ownership-controls '{
      "Rules": [
        {
          "ObjectOwnership": "BucketOwnerEnforced"
        }
      ]
    }'
}

ensure_lock_table() {
  local describe_output

  if describe_output="$(aws_cmd dynamodb describe-table --table-name "${LOCK_TABLE}" 2>&1)"; then
    echo "DynamoDB lock table already exists: ${LOCK_TABLE}"
    return
  fi

  if ! grep -q "ResourceNotFoundException" <<<"${describe_output}"; then
    echo "Unable to determine DynamoDB table status for ${LOCK_TABLE}:" >&2
    echo "${describe_output}" >&2
    exit 1
  fi

  echo "Creating DynamoDB lock table: ${LOCK_TABLE}"
  aws_cmd dynamodb create-table \
    --table-name "${LOCK_TABLE}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST >/dev/null

  aws_cmd dynamodb wait table-exists --table-name "${LOCK_TABLE}"
}

main() {
  echo "Terraform backend bootstrap"
  echo "Account: ${AWS_ACCOUNT_ID}"
  echo "Caller: ${CALLER_ARN}"
  echo "Region: ${AWS_REGION}"
  echo "Environment: ${ENVIRONMENT}"
  echo "State bucket: ${STATE_BUCKET}"
  echo "Lock table: ${LOCK_TABLE}"

  validate_region
  ensure_bucket
  configure_bucket
  ensure_lock_table

  echo "Backend bootstrap complete."
  echo "State bucket: ${STATE_BUCKET}"
  echo "Lock table: ${LOCK_TABLE}"
}

main "$@"
