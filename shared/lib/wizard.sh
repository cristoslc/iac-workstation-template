#!/usr/bin/env bash
# Shared bootstrap wizard logic using gum.
# Sourced by platform-specific bootstrap scripts and scripts/transfer-key.sh.
#
# NOTE: setup_logging() was removed intentionally — the exec > >(tee) approach
# breaks gum's isatty() check, making the TUI unusable. Bootstrap logging will
# move to the Textual TUI (setup.sh → setup_tui/) in a future phase.

# Colors for non-gum output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Run the bootstrap wizard. Sets exported variables:
#   BOOTSTRAP_MODE: fresh | new_account | existing_account
#   APPLY_SYSTEM_ROLES: true | false
#   APPLY_MACOS_DEFAULTS: true | false
#   SELECTED_PHASES: comma-separated list of phase tags
run_wizard() {
  echo ""
  gum style \
    --border normal \
    --border-foreground 4 \
    --padding "1 2" \
    --margin "0 0 1 0" \
    "Workstation Bootstrap"

  # Mode selection
  BOOTSTRAP_MODE=$(gum choose \
    --header "What kind of system is this?" \
    "Fresh install (new OS, clean slate)" \
    "Existing system, new user account" \
    "Existing system, existing user account")

  case "$BOOTSTRAP_MODE" in
    "Fresh install"*)
      BOOTSTRAP_MODE="fresh"
      APPLY_SYSTEM_ROLES=true
      APPLY_MACOS_DEFAULTS=true
      ;;
    "Existing system, new"*)
      BOOTSTRAP_MODE="new_account"
      APPLY_SYSTEM_ROLES=false
      APPLY_MACOS_DEFAULTS=true
      ;;
    "Existing system, existing"*)
      BOOTSTRAP_MODE="existing_account"
      APPLY_SYSTEM_ROLES=false
      APPLY_MACOS_DEFAULTS=false
      ;;
  esac

  # Role group selection
  local all_phases=("System" "Security" "Dev Tools" "Desktop" "Dotfiles")
  local default_phases

  if [ "$BOOTSTRAP_MODE" = "fresh" ]; then
    default_phases=("System" "Security" "Dev Tools" "Desktop" "Dotfiles")
  else
    default_phases=("Security" "Dev Tools" "Desktop" "Dotfiles")
  fi

  echo ""
  SELECTED_PHASES=$(gum choose \
    --no-limit \
    --header "Which role groups should run?" \
    --selected "$(IFS=,; echo "${default_phases[*]}")" \
    "${all_phases[@]}")

  # Override system roles based on selection
  if echo "$SELECTED_PHASES" | grep -q "System"; then
    APPLY_SYSTEM_ROLES=true
  else
    APPLY_SYSTEM_ROLES=false
  fi

  # Age key status
  echo ""
  if [ -f "$HOME/.config/sops/age/keys.txt" ]; then
    gum style --foreground 2 "Age key found at ~/.config/sops/age/keys.txt"
  else
    gum style --foreground 3 "Age key not found at ~/.config/sops/age/keys.txt"
    gum style --foreground 3 "Secrets decryption will be attempted via 1Password CLI."
    gum style --foreground 3 "If that fails, place your key and re-run bootstrap."
  fi

  # Summary
  echo ""
  gum style \
    --border normal \
    --border-foreground 6 \
    --padding "1 2" \
    "Mode: $BOOTSTRAP_MODE
System roles: $APPLY_SYSTEM_ROLES
Phases: $(echo "$SELECTED_PHASES" | tr '\n' ', ' | sed 's/,$//')"

  if ! gum confirm "Proceed with bootstrap?"; then
    echo "Bootstrap cancelled."
    exit 0
  fi

  export BOOTSTRAP_MODE
  export APPLY_SYSTEM_ROLES
  export APPLY_MACOS_DEFAULTS
  export SELECTED_PHASES
}

# Resolve the age private key.
# Returns 0 if key is available, 1 if not.
resolve_age_key() {
  local key_path="$HOME/.config/sops/age/keys.txt"
  local key_dir
  key_dir="$(dirname "$key_path")"

  # Already exists
  if [ -f "$key_path" ]; then
    chmod 700 "$key_dir"
    chmod 600 "$key_path"
    info "Age key found at $key_path"
    return 0
  fi

  # Try 1Password CLI
  if command -v op &>/dev/null; then
    info "Attempting to retrieve age key from 1Password..."
    (umask 077 && mkdir -p "$key_dir")
    local key_tmp
    key_tmp="$(mktemp)"
    if op read "op://Private/age-key/private-key" > "$key_tmp" 2>/dev/null && [ -s "$key_tmp" ]; then
      mv "$key_tmp" "$key_path"
      chmod 600 "$key_path"
      info "Age key retrieved from 1Password."
      return 0
    else
      rm -f "$key_tmp"
      warn "Could not retrieve age key from 1Password (not signed in?)."
    fi
  fi

  # Offer import from another machine (if age is installed and gum is available)
  if command -v age &>/dev/null && command -v gum &>/dev/null; then
    echo ""
    warn "Age key not found locally or via 1Password."
    local repo_dir
    repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    local transfer_script="$repo_dir/scripts/transfer-key.sh"

    # Validate the resolved path is inside the repo (prevents symlink traversal).
    if [[ "$transfer_script" != "$repo_dir/"* ]]; then
      warn "Unexpected transfer script path: $transfer_script. Skipping import."
    elif [ -f "$transfer_script" ]; then
      local import_method
      if command -v uv &>/dev/null; then
        import_method=$(gum choose \
          --header "Import age key from another machine?" \
          "Receive via Magic Wormhole (run 'make key-send' on source)" \
          "Paste encrypted blob (run 'make key-export' on source)" \
          "Skip — I'll set it up later")
      else
        import_method=$(gum choose \
          --header "Import age key from another machine?" \
          "Paste encrypted blob (run 'make key-export' on source)" \
          "Skip — I'll set it up later")
      fi

      case "$import_method" in
        "Receive via"*)
          bash "$transfer_script" receive
          [ -f "$key_path" ] && return 0
          ;;
        "Paste"*)
          bash "$transfer_script" import
          [ -f "$key_path" ] && return 0
          ;;
      esac
    fi
  fi

  # Neither available
  warn "Age key not available. Secrets will not be decrypted."
  warn "To enable secrets, place your age private key at:"
  warn "  $key_path"
  warn "Or on another machine with the key, run: make key-send"
  warn "Then re-run setup."
  return 1
}

# Install gum if not present.
# Expects PLATFORM to be set (linux or macos).
ensure_gum() {
  if command -v gum &>/dev/null; then
    return 0
  fi

  info "Installing gum..."
  case "${PLATFORM:-}" in
    linux)
      # Install via .deb from GitHub releases (pinned version + checksum)
      local gum_version="0.17.0"
      local gum_sha256="4c59b09c7248ea03c1544a11506b1152b1d8bd20e602fb2c2e9d158204d1f490"
      local gum_deb
      gum_deb="$(mktemp --suffix=.deb)"
      curl -fsSL "https://github.com/charmbracelet/gum/releases/download/v${gum_version}/gum_${gum_version}_amd64.deb" -o "$gum_deb"
      local actual_sha256
      actual_sha256="$(sha256sum "$gum_deb" | awk '{print $1}')"
      if [ "$actual_sha256" != "$gum_sha256" ]; then
        rm -f "$gum_deb"
        error "gum checksum mismatch! Expected: $gum_sha256, Got: $actual_sha256"
        exit 1
      fi
      sudo dpkg -i "$gum_deb"
      rm -f "$gum_deb"
      ;;
    macos)
      brew install gum
      ;;
    *)
      error "Cannot install gum: unknown platform."
      exit 1
      ;;
  esac
}
