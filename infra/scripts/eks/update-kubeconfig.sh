#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-logistics-platform-dev}"
REGION="${AWS_REGION:-${REGION:-us-east-1}}"
KUBECONFIG_PATH="${KUBECONFIG_PATH:-}"
CONTEXT_ALIAS="${CONTEXT_ALIAS:-$CLUSTER_NAME}"
PROFILE="${AWS_PROFILE:-}"
ROLE_ARN="${EKS_ROLE_ARN:-${ROLE_ARN:-}}"

usage() {
  cat <<EOF
Usage: $(basename "$0")

Environment variables:
  CLUSTER_NAME     EKS cluster name. Default: logistics-platform-dev
  REGION           AWS region. Default: us-east-1
  AWS_PROFILE      Optional AWS CLI profile
  ROLE_ARN         Optional IAM role ARN for kubectl authentication
  KUBECONFIG_PATH  Optional kubeconfig output path
  CONTEXT_ALIAS    Optional kubeconfig context alias
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

require_command aws
require_command kubectl

echo "Using AWS IAM identity:" >&2
aws_cmd sts get-caller-identity >&2

endpoint_public_access="$(aws_cmd eks describe-cluster --region "$REGION" --name "$CLUSTER_NAME" --query 'cluster.resourcesVpcConfig.endpointPublicAccess' --output text)"
endpoint_private_access="$(aws_cmd eks describe-cluster --region "$REGION" --name "$CLUSTER_NAME" --query 'cluster.resourcesVpcConfig.endpointPrivateAccess' --output text)"

if [[ "$endpoint_public_access" == "False" && "$endpoint_private_access" == "True" ]]; then
  echo "Cluster endpoint is private-only. Run kubectl from inside the VPC or a connected network." >&2
fi

update_cmd=(eks update-kubeconfig --region "$REGION" --name "$CLUSTER_NAME" --alias "$CONTEXT_ALIAS")
if [[ -n "$KUBECONFIG_PATH" ]]; then
  update_cmd+=(--kubeconfig "$KUBECONFIG_PATH")
fi
if [[ -n "$ROLE_ARN" ]]; then
  update_cmd+=(--role-arn "$ROLE_ARN")
fi

echo "Writing kubeconfig for cluster ${CLUSTER_NAME} in ${REGION}." >&2
aws_cmd "${update_cmd[@]}"

token_cmd=(eks get-token --region "$REGION" --cluster-name "$CLUSTER_NAME")
if [[ -n "$ROLE_ARN" ]]; then
  token_cmd+=(--role-arn "$ROLE_ARN")
fi
aws_cmd "${token_cmd[@]}" >/dev/null

echo "Kubeconfig updated and IAM token generation succeeded." >&2
echo "Next step: kubectl config use-context ${CONTEXT_ALIAS}" >&2

