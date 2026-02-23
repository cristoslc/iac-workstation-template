#!/usr/bin/env bash
set -euo pipefail

# Check for filename collisions between shared and platform dotfile stow packages.
# A collision occurs when the same relative file path exists in both shared and platform dotfiles.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(dirname "$SCRIPT_DIR")}"

SHARED_DIR="${SHARED_DIR:-$REPO_DIR/shared/dotfiles}"
COLLISIONS=0

check_collisions() {
  local platform_dir="$1"
  local platform_name="$2"

  if [ ! -d "$platform_dir" ]; then
    return
  fi

  # For each stow package in the platform
  for pkg_dir in "$platform_dir"/*/; do
    [ -d "$pkg_dir" ] || continue
    local pkg_name
    pkg_name=$(basename "$pkg_dir")

    local shared_pkg="$SHARED_DIR/$pkg_name"
    [ -d "$shared_pkg" ] || continue

    # Find all files in the platform package
    while IFS= read -r -d '' file; do
      local relative="${file#$pkg_dir}"
      local shared_file="$shared_pkg/$relative"

      if [ -f "$shared_file" ]; then
        echo "COLLISION: $pkg_name/$relative exists in both shared and $platform_name"
        COLLISIONS=$((COLLISIONS + 1))
      fi
    done < <(find "$pkg_dir" -type f -print0)
  done
}

# Allow sourcing for tests without executing main logic.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "Checking stow filename collisions..."
  check_collisions "$REPO_DIR/linux/dotfiles" "linux"
  check_collisions "$REPO_DIR/macos/dotfiles" "macos"

  # Also check secrets dotfiles
  check_collisions "$REPO_DIR/shared/secrets/dotfiles" "shared-secrets"
  check_collisions "$REPO_DIR/linux/secrets/dotfiles" "linux-secrets"
  check_collisions "$REPO_DIR/macos/secrets/dotfiles" "macos-secrets"

  if [ "$COLLISIONS" -gt 0 ]; then
    echo ""
    echo "Found $COLLISIONS collision(s). Rename files to avoid conflicts."
    exit 1
  else
    echo "No collisions found."
    exit 0
  fi
fi
