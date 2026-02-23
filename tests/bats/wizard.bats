#!/usr/bin/env bats

load helpers/setup

SCRIPT_DIR="$(cd "$(dirname "${BATS_TEST_FILENAME}")/../.." && pwd)"

setup() {
  TEST_TEMP="$(mktemp -d)"
  export TEST_TEMP

  source "$SCRIPT_DIR/shared/lib/wizard.sh"
}

teardown() {
  rm -rf "$TEST_TEMP"
}

# --- info / warn / error output format ---

@test "info: prints [INFO] prefix" {
  run info "hello world"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[INFO]"* ]]
  [[ "$output" == *"hello world"* ]]
}

@test "warn: prints [WARN] prefix" {
  run warn "caution here"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[WARN]"* ]]
  [[ "$output" == *"caution here"* ]]
}

@test "error: prints [ERROR] prefix" {
  run error "something broke"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[ERROR]"* ]]
  [[ "$output" == *"something broke"* ]]
}

# --- resolve_age_key ---

@test "resolve_age_key: returns 0 when key exists" {
  export HOME="$TEST_TEMP/home"
  mkdir -p "$HOME/.config/sops/age"
  echo "AGE-SECRET-KEY-1FAKE" > "$HOME/.config/sops/age/keys.txt"

  run resolve_age_key
  [ "$status" -eq 0 ]
}

@test "resolve_age_key: returns 1 when key missing and no 1password" {
  export HOME="$TEST_TEMP/home"
  mkdir -p "$HOME"

  # Create a wrapper that hides op from command -v but keeps system PATH intact.
  _test_resolve_no_op() {
    # Override command to hide op
    command() {
      if [[ "$1" == "-v" && "$2" == "op" ]]; then
        return 1
      fi
      builtin command "$@"
    }
    resolve_age_key
  }

  run _test_resolve_no_op
  [ "$status" -eq 1 ]
  [[ "$output" == *"not available"* ]]
}

@test "resolve_age_key: sets correct permissions on key file" {
  export HOME="$TEST_TEMP/home"
  mkdir -p "$HOME/.config/sops/age"
  echo "AGE-SECRET-KEY-1FAKE" > "$HOME/.config/sops/age/keys.txt"
  chmod 644 "$HOME/.config/sops/age/keys.txt"

  resolve_age_key

  # Key file should be 600
  local perms
  perms=$(stat -f "%Lp" "$HOME/.config/sops/age/keys.txt" 2>/dev/null || stat -c "%a" "$HOME/.config/sops/age/keys.txt" 2>/dev/null)
  [ "$perms" = "600" ]
}
