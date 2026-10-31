#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-logistics-platform-dev}"
REGION="${AWS_REGION:-${REGION:-us-east-1}}"
PROFILE="${AWS_PROFILE:-}"
ROLE_ARN="${EKS_ROLE_ARN:-${ROLE_ARN:-}}"
CONTEXT_ALIAS="${CONTEXT_ALIAS:-$CLUSTER_NAME}"

usage() {
  cat <<EOF
Usage: $(basename "$0")

Environment variables:
  CLUSTER_NAME   EKS cluster name. Default: logistics-platform-dev
  REGION         AWS region. Default: us-east-1
  AWS_PROFILE    Optional AWS CLI profile
  ROLE_ARN       Optional IAM role ARN for kubectl authentication
  CONTEXT_ALIAS  Optional kubeconfig context alias
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

echo "Verifying AWS IAM identity:" >&2
aws_cmd sts get-caller-identity >&2

token_cmd=(eks get-token --region "$REGION" --cluster-name "$CLUSTER_NAME")
if [[ -n "$ROLE_ARN" ]]; then
  token_cmd+=(--role-arn "$ROLE_ARN")
fi
aws_cmd "${token_cmd[@]}" >/dev/null
echo "IAM token generation succeeded." >&2

kubectl config use-context "$CONTEXT_ALIAS" >/dev/null
kubectl cluster-info

if kubectl get namespace kube-system --request-timeout=15s >/dev/null; then
  echo "kubectl access verified for cluster ${CLUSTER_NAME}." >&2
else
  echo "Authenticated, but Kubernetes authorization may be missing for this IAM principal." >&2
  echo "Check EKS access entries or RBAC bindings for the current IAM identity." >&2
  exit 1
fi

