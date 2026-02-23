#!/usr/bin/env bash
# Shared test helpers for bats-core tests.

# Create a temporary directory for each test, cleaned up automatically.
setup() {
  TEST_TEMP="$(mktemp -d)"
  export TEST_TEMP
}

teardown() {
  rm -rf "$TEST_TEMP"
}

# Create a file with optional content.
# Usage: create_file <path> [content]
create_file() {
  local path="$1"
  local content="${2:-}"
  mkdir -p "$(dirname "$path")"
  echo "$content" > "$path"
}

# Create a symlink.
# Usage: create_symlink <target> <link_path>
create_symlink() {
  local target="$1"
  local link_path="$2"
  mkdir -p "$(dirname "$link_path")"
  ln -sf "$target" "$link_path"
}
