#!/usr/bin/env bash
set -euo pipefail
umask 077

# First-run shim: installs prerequisites (age, sops, gum, gh, uv), then hands
# off to the Python wizard for all interactive logic.
# Usage: ./first-run.sh [--debug]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect platform
case "$(uname -s)" in
  Linux*)  PLATFORM="linux" ;;
  Darwin*) PLATFORM="macos" ;;
  *)
    echo "Unsupported OS: $(uname -s)"
    exit 1
    ;;
esac
export PLATFORM

# Source shared helpers (info, warn, error, ensure_gum)
source "$SCRIPT_DIR/shared/lib/wizard.sh"

trap 'error "First-run failed at prerequisite installation stage."' ERR

# =============================================================================
# Install prerequisites (must happen before Python)
# =============================================================================

info "Checking and installing prerequisites..."

install_prereqs_linux() {
  sudo apt-get update -qq

  # age
  if ! command -v age &>/dev/null; then
    info "Installing age..."
    sudo apt-get install -y -qq age
  fi

  # sops (pinned version + checksum)
  if ! command -v sops &>/dev/null; then
    info "Installing sops..."
    local sops_version="3.9.4"
    local sops_sha256="e18a091c45888f82e1a7fd14561ebb913872441f92c8162d39bb63eb9308dd16"
    local sops_deb
    sops_deb="$(mktemp --suffix=.deb)"
    curl -fsSL "https://github.com/getsops/sops/releases/download/v${sops_version}/sops_${sops_version}_amd64.deb" -o "$sops_deb"
    local actual_sha256
    actual_sha256="$(sha256sum "$sops_deb" | awk '{print $1}')"
    if [ "$actual_sha256" != "$sops_sha256" ]; then
      rm -f "$sops_deb"
      error "sops checksum mismatch! Expected: $sops_sha256, Got: $actual_sha256"
      exit 1
    fi
    sudo dpkg -i "$sops_deb"
    rm -f "$sops_deb"
  fi

  # gh CLI
  if ! command -v gh &>/dev/null; then
    info "Installing GitHub CLI..."
    sudo mkdir -p -m 755 /etc/apt/keyrings
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
    sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq gh
  fi

  # gum
  ensure_gum
}

install_prereqs_macos() {
  # Xcode CLT
  if ! xcode-select -p &>/dev/null; then
    info "Installing Xcode Command Line Tools..."
    xcode-select --install
    until xcode-select -p &>/dev/null; do sleep 5; done
  fi

  # Homebrew — pin installer to a specific commit to prevent supply chain attacks.
  # Update this SHA when you want to pull in a newer installer version:
  #   git ls-remote https://github.com/Homebrew/install.git HEAD
  local brew_commit="0e1bf654fd95d1ddebe83b1f8c77de6e2c1b7cfe"
  if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    local brew_installer
    brew_installer="$(mktemp)"
    curl -fsSL "https://raw.githubusercontent.com/Homebrew/install/${brew_commit}/install.sh" -o "$brew_installer"
    /bin/bash "$brew_installer"
    rm -f "$brew_installer"
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi

  # Install all prereqs via brew (no gettext — Python replaces envsubst)
  info "Installing prerequisites via Homebrew..."
  brew install age sops gum gh 2>/dev/null || true
}

if [ "$PLATFORM" = "linux" ]; then
  install_prereqs_linux
else
  install_prereqs_macos
fi

# =============================================================================
# Ensure uv is available (needed to run the Python wizard)
# =============================================================================

if ! command -v uv &>/dev/null; then
  info "Installing uv..."
  # Download then execute (not pipe-to-shell).
  # NOTE: No checksum verification here (bootstrap chicken-and-egg). The Ansible
  # python role pins uv to a specific version with SHA-256 verification.
  uv_installer="$(mktemp)"
  curl -LsSf https://astral.sh/uv/install.sh -o "$uv_installer"
  sh "$uv_installer"
  rm -f "$uv_installer"
  export PATH="$HOME/.local/bin:$PATH"
fi

# =============================================================================
# Hand off to the Python wizard
# =============================================================================

# Clear the ERR trap — Python handles its own error reporting.
trap - ERR

# exec replaces this shell process with Python (no bash runs after this line).
exec uv run --with rich,pyyaml "$SCRIPT_DIR/scripts/first-run.py" "$@"
