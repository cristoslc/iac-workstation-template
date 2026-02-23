#!/usr/bin/env bash
set -euo pipefail
umask 077

# Tell SOPS where to find the age key (macOS defaults to ~/Library/Application Support/).
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"

# Decrypt all .sops files in a secrets/ directory to .decrypted/ counterparts.
# Usage: ./scripts/decrypt-secrets.sh <secrets-dir>
# Example: ./scripts/decrypt-secrets.sh shared/secrets

# Compute the decrypted output path for a given SOPS-encrypted file.
# Strips the .sops segment while preserving the file extension.
#   vars.sops.yml  → vars.yml
#   vars.sops.yaml → vars.yaml
#   secrets.zsh.sops → secrets.zsh
compute_output_path() {
  local decrypted_dir="$1"
  local relative="$2"

  if [[ "$relative" == *.sops.yml ]] || [[ "$relative" == *.sops.yaml ]]; then
    echo "$decrypted_dir/${relative/.sops/}"
  else
    echo "$decrypted_dir/${relative%.sops}"
  fi
}

# Allow sourcing for tests without executing main logic.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  SECRETS_DIR="${1:?Usage: $0 <secrets-dir>}"
  DECRYPTED_DIR="$SECRETS_DIR/.decrypted"

  if [ ! -d "$SECRETS_DIR" ]; then
    echo "Directory not found: $SECRETS_DIR"
    exit 1
  fi

  # Find all .sops and .sops.yml files (excluding .decrypted/ itself)
  find "$SECRETS_DIR" -path "$DECRYPTED_DIR" -prune -o \( -name "*.sops" -o -name "*.sops.yml" -o -name "*.sops.yaml" \) -print | while read -r encrypted_file; do
    relative="${encrypted_file#$SECRETS_DIR/}"
    decrypted_file="$(compute_output_path "$DECRYPTED_DIR" "$relative")"

    # Create parent directory (explicit mode as defense-in-depth alongside umask).
    # shellcheck disable=SC2174  # -m only applies to deepest dir; parents inherit umask 077
    mkdir -p -m 700 "$(dirname "$decrypted_file")"

    # Decrypt
    echo "Decrypting: $encrypted_file -> $decrypted_file"
    sops -d "$encrypted_file" > "$decrypted_file"
    chmod 600 "$decrypted_file"
  done

  echo "Done. Decrypted files are in $DECRYPTED_DIR/"
fi
