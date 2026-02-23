#!/usr/bin/env bash
set -euo pipefail
umask 077

# Root entry point: detects OS and delegates to platform-specific bootstrap.
# Usage: ./bootstrap.sh [clone-path]

WORKSTATION_DIR="${1:-$HOME/.workstation}"

case "$(uname -s)" in
  Linux*)  PLATFORM="linux" ;;
  Darwin*) PLATFORM="macos" ;;
  *)
    echo "Unsupported OS: $(uname -s)"
    exit 1
    ;;
esac

# Determine script location (handles both cloned repo and symlinked cases)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# If running from the cloned repo, use it directly.
# If not (e.g., curl one-liner), clone first.
if [ ! -f "$SCRIPT_DIR/$PLATFORM/bootstrap.sh" ]; then
  echo "Cloning repository to $WORKSTATION_DIR..."
  if [ "$PLATFORM" = "linux" ]; then
    sudo apt-get update -qq && sudo apt-get install -y -qq git
  else
    xcode-select --install 2>/dev/null || true
    until xcode-select -p &>/dev/null; do sleep 5; done
  fi
  git clone "${GITHUB_REPO_URL}" "$WORKSTATION_DIR"
  SCRIPT_DIR="$WORKSTATION_DIR"
fi

exec "$SCRIPT_DIR/$PLATFORM/bootstrap.sh" "$WORKSTATION_DIR"
