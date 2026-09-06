#!/bin/bash
# Fetch a clean source tree, preserving any machine-specific edits in ~/ok-extras.
set -euo pipefail
if (( EUID != 0 )); then
  echo 'Run: sudo bash update.sh' >&2
  exit 1
fi
stage=$(mktemp -d /var/tmp/ok-extras-update-XXXXXXXX)
trap 'rm -rf -- "$stage"' EXIT
git clone --depth 1 --branch main https://github.com/mandrigin/ok-extras.git "$stage/source"
bash "$stage/source/upgrade.sh"
