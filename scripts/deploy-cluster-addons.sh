#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Default is a command plan. Opt in explicitly; phases 2/3 require private EKS access.
exec python3 "${SCRIPT_DIR}/bootstrap/bootstrap.py" --environment "${ENVIRONMENT:-dev}" --phase 2 "$@"
