#!/usr/bin/env bash
set -euo pipefail

# Show differences between stowed dotfiles and actual files in $HOME.
# Useful for detecting drift.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(dirname "$SCRIPT_DIR")}"

check_links() {
  local dotfiles_dir="$1"
  local label="$2"
  local target_dir="${3:-$HOME}"

  [ -d "$dotfiles_dir" ] || return 0

  for pkg_dir in "$dotfiles_dir"/*/; do
    [ -d "$pkg_dir" ] || continue
    local pkg_name
    pkg_name=$(basename "$pkg_dir")

    while IFS= read -r -d '' file; do
      local relative="${file#$pkg_dir}"
      local target="$target_dir/$relative"

      if [ -L "$target" ]; then
        local link_target
        link_target=$(readlink "$target")
        if [[ "$link_target" == *"$relative"* ]]; then
          # Symlink points to expected location
          :
        else
          echo "MISMATCH [$label/$pkg_name]: $target -> $link_target (expected to point to repo)"
        fi
      elif [ -f "$target" ]; then
        echo "NOT LINKED [$label/$pkg_name]: $target exists as a real file (not symlinked)"
      else
        echo "MISSING [$label/$pkg_name]: $target does not exist"
      fi
    done < <(find "$pkg_dir" -type f -print0)
  done
}

# Allow sourcing for tests without executing main logic.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "Checking dotfile symlinks..."

  check_links "$REPO_DIR/shared/dotfiles" "shared"
  check_links "$REPO_DIR/linux/dotfiles" "linux"
  check_links "$REPO_DIR/macos/dotfiles" "macos"

  echo "Done."
fi
