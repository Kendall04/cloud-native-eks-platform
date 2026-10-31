#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-logistics-platform-dev}"
REGION="${AWS_REGION:-${REGION:-us-east-1}}"
PROFILE="${AWS_PROFILE:-}"
PRINCIPAL_ARN="${PRINCIPAL_ARN:-}"
POLICY_ARN="${POLICY_ARN:-arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy}"
ACCESS_SCOPE="${ACCESS_SCOPE:-type=cluster}"

usage() {
  cat <<EOF
Usage: PRINCIPAL_ARN=<iam-principal-arn> $(basename "$0")

Environment variables:
  PRINCIPAL_ARN  Required IAM role or user ARN to authorize
  CLUSTER_NAME   EKS cluster name. Default: logistics-platform-dev
  REGION         AWS region. Default: us-east-1
  AWS_PROFILE    Optional AWS CLI profile
  POLICY_ARN     Optional EKS access policy ARN
  ACCESS_SCOPE   Optional access scope. Default: type=cluster
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

aws_cmd() {
  local cmd=(aws)
  if [[ -n "$PROFILE" ]]; then
    cmd+=(--profile "$PROFILE")
  fi
  cmd+=("$@")
  "${cmd[@]}"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -z "$PRINCIPAL_ARN" ]]; then
  usage >&2
  exit 1
fi

require_command aws

auth_mode="$(aws_cmd eks describe-cluster --region "$REGION" --name "$CLUSTER_NAME" --query 'cluster.accessConfig.authenticationMode' --output text)"
if [[ "$auth_mode" != "API" && "$auth_mode" != "API_AND_CONFIG_MAP" ]]; then
  echo "Cluster authentication mode is ${auth_mode}. Access entries require API or API_AND_CONFIG_MAP." >&2
  exit 1
fi

existing_entries="$(aws_cmd eks list-access-entries --region "$REGION" --cluster-name "$CLUSTER_NAME" --query 'accessEntries[]' --output text || true)"
if ! printf '%s\n' "$existing_entries" | tr '\t' '\n' | grep -Fxq "$PRINCIPAL_ARN"; then
  aws_cmd eks create-access-entry \
    --region "$REGION" \
    --cluster-name "$CLUSTER_NAME" \
    --principal-arn "$PRINCIPAL_ARN" \
    --type STANDARD
fi

associated_policies="$(aws_cmd eks list-associated-access-policies --region "$REGION" --cluster-name "$CLUSTER_NAME" --principal-arn "$PRINCIPAL_ARN" --query 'associatedAccessPolicies[].policyArn' --output text || true)"
if ! printf '%s\n' "$associated_policies" | tr '\t' '\n' | grep -Fxq "$POLICY_ARN"; then
  aws_cmd eks associate-access-policy \
    --region "$REGION" \
    --cluster-name "$CLUSTER_NAME" \
    --principal-arn "$PRINCIPAL_ARN" \
    --policy-arn "$POLICY_ARN" \
    --access-scope "$ACCESS_SCOPE"
fi

echo "Access entry and policy association verified for ${PRINCIPAL_ARN}." >&2

