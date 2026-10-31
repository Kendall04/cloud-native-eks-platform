#!/usr/bin/env bash
# Linux x86_64 CI tools; fixed versions and reviewed upstream checksums.
set -euo pipefail
destination="${1:-${RUNNER_TEMP:-/tmp}/cnp-ci-tools}"
mkdir -p "$destination"
archive="$destination/trivy.tar.gz"
curl --fail --silent --show-error --location --retry 3 \
  https://github.com/aquasecurity/trivy/releases/download/v0.71.2/trivy_0.71.2_Linux-64bit.tar.gz -o "$archive"
echo "0510e71e2fd39bf863856d499c8dc19feb4e7336546394c502a8f5cc7ab27460  $archive" | sha256sum --check --status
tar -xzf "$archive" -C "$destination" trivy
rm "$archive"
"$destination/trivy" --version
if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "$destination" >> "$GITHUB_PATH"
fi
