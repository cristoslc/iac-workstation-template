#!/usr/bin/env bats

load helpers/setup

SCRIPT_DIR="$(cd "$(dirname "${BATS_TEST_FILENAME}")/../.." && pwd)"

setup() {
  TEST_TEMP="$(mktemp -d)"
  export TEST_TEMP

  export REPO_DIR="$TEST_TEMP/repo"
  export FAKE_HOME="$TEST_TEMP/home"
  mkdir -p "$REPO_DIR/shared/dotfiles"
  mkdir -p "$FAKE_HOME"

  # Source the script (loads check_links function without executing main)
  source "$SCRIPT_DIR/scripts/diff-dotfiles.sh"
}

teardown() {
  rm -rf "$TEST_TEMP"
}

@test "correct symlink: no output" {
  # Create a dotfile in the repo
  mkdir -p "$REPO_DIR/shared/dotfiles/git"
  echo "config" > "$REPO_DIR/shared/dotfiles/git/.gitconfig"

  # Create a correct symlink in fake home
  mkdir -p "$FAKE_HOME"
  ln -sf "$REPO_DIR/shared/dotfiles/git/.gitconfig" "$FAKE_HOME/.gitconfig"

  run check_links "$REPO_DIR/shared/dotfiles" "shared" "$FAKE_HOME"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "missing file: reports MISSING" {
  mkdir -p "$REPO_DIR/shared/dotfiles/git"
  echo "config" > "$REPO_DIR/shared/dotfiles/git/.gitconfig"

  # No file at all in fake home
  run check_links "$REPO_DIR/shared/dotfiles" "shared" "$FAKE_HOME"
  [ "$status" -eq 0 ]
  [[ "$output" == *"MISSING"* ]]
  [[ "$output" == *".gitconfig"* ]]
}

@test "real file: reports NOT LINKED" {
  mkdir -p "$REPO_DIR/shared/dotfiles/git"
  echo "config" > "$REPO_DIR/shared/dotfiles/git/.gitconfig"

  # Real file (not a symlink) in fake home
  echo "local config" > "$FAKE_HOME/.gitconfig"

  run check_links "$REPO_DIR/shared/dotfiles" "shared" "$FAKE_HOME"
  [ "$status" -eq 0 ]
  [[ "$output" == *"NOT LINKED"* ]]
}

@test "wrong symlink: reports MISMATCH" {
  mkdir -p "$REPO_DIR/shared/dotfiles/git"
  echo "config" > "$REPO_DIR/shared/dotfiles/git/.gitconfig"

  # Symlink pointing to wrong location
  echo "wrong" > "$TEST_TEMP/wrong-target"
  ln -sf "$TEST_TEMP/wrong-target" "$FAKE_HOME/.gitconfig"

  run check_links "$REPO_DIR/shared/dotfiles" "shared" "$FAKE_HOME"
  [ "$status" -eq 0 ]
  [[ "$output" == *"MISMATCH"* ]]
}

@test "nonexistent dotfiles dir: no output, no error" {
  run check_links "$REPO_DIR/nonexistent" "nope" "$FAKE_HOME"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "nested dotfile paths work" {
  mkdir -p "$REPO_DIR/shared/dotfiles/zsh/.config/zsh"
  echo "aliases" > "$REPO_DIR/shared/dotfiles/zsh/.config/zsh/aliases.zsh"

  # File is missing in home
  run check_links "$REPO_DIR/shared/dotfiles" "shared" "$FAKE_HOME"
  [ "$status" -eq 0 ]
  [[ "$output" == *"MISSING"* ]]
  [[ "$output" == *"aliases.zsh"* ]]
}
