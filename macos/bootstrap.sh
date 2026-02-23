#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PLATFORM="macos"

# Ensure tools installed to ~/.local/bin are visible (uv, ansible, etc.).
export PATH="$HOME/.local/bin:$PATH"

# Source shared wizard
source "$SCRIPT_DIR/../shared/lib/wizard.sh"

trap 'error "Bootstrap failed. Re-run after fixing the issue above."' ERR

# --- Phase 1: Install Xcode CLT ---

if ! xcode-select -p &>/dev/null; then
  info "Installing Xcode Command Line Tools..."
  xcode-select --install
  info "Waiting for Xcode CLT installation to complete..."
  until xcode-select -p &>/dev/null; do sleep 5; done
fi

# --- Phase 2: Install Homebrew ---

# Pin Homebrew installer to a specific commit to prevent supply chain attacks.
# Update this SHA when you want to pull in a newer installer version:
#   git ls-remote https://github.com/Homebrew/install.git HEAD
BREW_INSTALL_COMMIT="0e1bf654fd95d1ddebe83b1f8c77de6e2c1b7cfe"
if ! command -v brew &>/dev/null; then
  info "Installing Homebrew..."
  brew_installer="$(mktemp)"
  curl -fsSL "https://raw.githubusercontent.com/Homebrew/install/${BREW_INSTALL_COMMIT}/install.sh" -o "$brew_installer"
  /bin/bash "$brew_installer"
  rm -f "$brew_installer"
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# --- Phase 3: Install prerequisites via Homebrew ---

info "Installing prerequisites via Homebrew..."
brew install sops age stow gum 2>/dev/null || true

# --- Phase 4: Install uv and Ansible ---

# NOTE: uv is bootstrapped without checksum verification here because Ansible
# (installed via uv) is not yet available. The Ansible python role pins uv to a
# specific version with SHA-256 verification for subsequent installs.
if ! command -v uv &>/dev/null; then
  info "Installing uv..."
  uv_installer="$(mktemp)"
  curl -LsSf https://astral.sh/uv/install.sh -o "$uv_installer"
  sh "$uv_installer"
  rm -f "$uv_installer"
fi

if ! command -v ansible-playbook &>/dev/null; then
  info "Installing Ansible via uv..."
  uv tool install ansible-core
fi

# --- Phase 5: Install Ansible Galaxy collections ---

info "Installing Ansible Galaxy collections..."
ansible-galaxy collection install -r "$SCRIPT_DIR/../shared/requirements.yml"

# --- Phase 6: Run wizard ---

run_wizard

# --- Phase 7: Resolve age key ---

resolve_age_key || true

# --- Phase 8: Run Ansible ---

info "Running Ansible playbook..."
export ANSIBLE_CONFIG="$SCRIPT_DIR/ansible.cfg"
cd "$SCRIPT_DIR"

ansible-playbook site.yml \
  --ask-become-pass \
  -e "workstation_dir=$(dirname "$SCRIPT_DIR")" \
  -e "bootstrap_mode=$BOOTSTRAP_MODE" \
  -e "apply_system_roles=$APPLY_SYSTEM_ROLES" \
  -e "apply_macos_defaults=${APPLY_MACOS_DEFAULTS:-true}" \
  -e "platform=macos" \
  -e "platform_dir=macos"

info "Bootstrap complete!"
info "Some macOS defaults changes may require a restart."
