#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

exit_code=0

# --- yamllint (config in .yamllint.yml) ---

echo "Running yamllint..."
if command -v yamllint &>/dev/null; then
  yamllint "$REPO_DIR" --no-warnings || exit_code=1
else
  echo "yamllint not installed. Install with: pip install yamllint"
  exit_code=1
fi

# --- shellcheck ---

echo ""
echo "Running shellcheck..."
if command -v shellcheck &>/dev/null; then
  shellcheck --severity=warning \
    "$REPO_DIR"/bootstrap.sh \
    "$REPO_DIR"/first-run.sh \
    "$REPO_DIR"/linux/bootstrap.sh \
    "$REPO_DIR"/macos/bootstrap.sh \
    "$REPO_DIR"/shared/lib/wizard.sh \
    "$REPO_DIR"/scripts/lint.sh \
    "$REPO_DIR"/scripts/check-stow-collisions.sh \
    "$REPO_DIR"/scripts/diff-dotfiles.sh \
    "$REPO_DIR"/scripts/decrypt-secrets.sh \
    || exit_code=1
else
  echo "shellcheck not installed. Install with: brew install shellcheck"
  exit_code=1
fi

# --- ansible-lint ---

echo ""
echo "Running ansible-lint..."
if command -v ansible-lint &>/dev/null; then
  # Disable SOPS vars plugin — it requires an age key that won't exist in CI.
  export ANSIBLE_VARS_ENABLED=host_group_vars
  for platform in linux macos; do
    echo "  Linting $platform..."
    cd "$REPO_DIR/$platform"
    ANSIBLE_CONFIG="$REPO_DIR/$platform/ansible.cfg" ansible-lint site.yml || exit_code=1
  done
else
  echo "ansible-lint not installed. Install with: pip install ansible-lint"
  exit_code=1
fi

# --- stow collision check ---

echo ""
echo "Running stow collision check..."
"$REPO_DIR/scripts/check-stow-collisions.sh" || exit_code=1

# --- summary ---

echo ""
if [ "$exit_code" -ne 0 ]; then
  echo "Lint failed."
else
  echo "All checks passed."
fi
exit "$exit_code"
