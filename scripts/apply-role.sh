#!/usr/bin/env bash
# apply-role.sh — Run ansible-playbook for a single role with temporary
# NOPASSWD sudo.  Works around PAM fingerprint modules (e.g. pam_fprintd
# on Linux Mint) that hang Ansible's become prompt detection.
#
# Usage: scripts/apply-role.sh <platform-dir> <role> [extra ansible args...]

set -euo pipefail

PLATFORM_DIR="${1:?Usage: apply-role.sh <platform-dir> <role>}"
ROLE="${2:?Usage: apply-role.sh <platform-dir> <role>}"
shift 2

SUDOERS_TEMP="/etc/sudoers.d/99-apply-temp"

cleanup() {
    sudo -n rm -f "$SUDOERS_TEMP" 2>/dev/null || true
}
trap cleanup EXIT

# Collect sudo password and grant temporary NOPASSWD
read -rsp "BECOME password: " BECOME_PASS
echo

printf '%s\n' "$BECOME_PASS" | sudo -S sh -c \
    "printf '%s ALL=(ALL) NOPASSWD: ALL\n' '$(whoami)' > '$SUDOERS_TEMP' \
     && chmod 0440 '$SUDOERS_TEMP'"

# Run the playbook without --ask-become-pass
cd "$PLATFORM_DIR"
ansible-playbook site.yml --tags "$ROLE" "$@"
