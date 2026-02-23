#!/usr/bin/env bash
set -euo pipefail
umask 077

# Unified entry point: installs minimal prerequisites (python3, uv), then
# hands off to the Textual TUI for all interactive logic.
# Usage: ./setup.sh [--debug] [--bootstrap]
#   --bootstrap  Skip menu, go straight to bootstrap flow
#   Or via curl one-liner:
#     bash <(curl -fsSL https://raw.githubusercontent.com/.../setup.sh)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect platform.
case "$(uname -s)" in
  Linux*)  PLATFORM="linux" ;;
  Darwin*) PLATFORM="macos" ;;
  *)
    echo "Unsupported OS: $(uname -s)"
    exit 1
    ;;
esac
export PLATFORM

# Ensure ~/.local/bin is on PATH (uv installs there).
export PATH="$HOME/.local/bin:$PATH"

# --- Clone repo if running outside a cloned checkout ---

if [ ! -f "$SCRIPT_DIR/scripts/setup.py" ]; then
  WORKSTATION_DIR="${1:-$HOME/.workstation}"
  echo "Cloning repository to $WORKSTATION_DIR..."
  if [ "$PLATFORM" = "linux" ]; then
    sudo apt-get update -qq && sudo apt-get install -y -qq git curl
  else
    xcode-select --install 2>/dev/null || true
    until xcode-select -p &>/dev/null; do sleep 5; done
  fi
  git clone "${GITHUB_REPO_URL}" "$WORKSTATION_DIR"
  exec "$WORKSTATION_DIR/setup.sh" "$@"
fi

# --- Ensure python3 is available ---

if [ "$PLATFORM" = "linux" ]; then
  if ! command -v python3 &>/dev/null; then
    echo "Installing python3..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3
  fi
else
  # macOS: Xcode CLT provides python3.
  if ! xcode-select -p &>/dev/null; then
    echo "Installing Xcode Command Line Tools..."
    xcode-select --install
    until xcode-select -p &>/dev/null; do sleep 5; done
  fi
fi

# --- Ensure uv is available ---

if ! command -v uv &>/dev/null; then
  echo "Installing uv..."
  uv_installer="$(mktemp)"
  curl -LsSf https://astral.sh/uv/install.sh -o "$uv_installer"
  sh "$uv_installer"
  rm -f "$uv_installer"
  export PATH="$HOME/.local/bin:$PATH"
fi

# --- Hand off to the Textual TUI ---

uv run --with textual,pyyaml "$SCRIPT_DIR/scripts/setup.py" "$@" || tui_exit=$?
tui_exit="${tui_exit:-0}"

# Exit code 7 = bootstrap succeeded, reload shell to pick up new dotfiles.
if [ "$tui_exit" -eq 7 ]; then
  echo "Reloading shell to apply updated configs..."
  exec "${SHELL:-/bin/bash}" -l
fi

exit "$tui_exit"
