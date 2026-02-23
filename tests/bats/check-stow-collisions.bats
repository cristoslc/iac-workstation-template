#!/usr/bin/env bats

load helpers/setup

SCRIPT_DIR="$(cd "$(dirname "${BATS_TEST_FILENAME}")/../.." && pwd)"

setup() {
  # Call shared setup (creates TEST_TEMP)
  TEST_TEMP="$(mktemp -d)"
  export TEST_TEMP

  # Set up a fake repo structure
  export REPO_DIR="$TEST_TEMP/repo"
  mkdir -p "$REPO_DIR/shared/dotfiles"
  mkdir -p "$REPO_DIR/linux/dotfiles"
  mkdir -p "$REPO_DIR/macos/dotfiles"
  export SHARED_DIR="$REPO_DIR/shared/dotfiles"

  # Source the script (loads check_collisions function without executing main)
  source "$SCRIPT_DIR/scripts/check-stow-collisions.sh"
}

teardown() {
  rm -rf "$TEST_TEMP"
}

@test "no collision: platform file has no shared counterpart" {
  # Platform has a file, shared does not have that package
  mkdir -p "$REPO_DIR/linux/dotfiles/git"
  echo "linux-only" > "$REPO_DIR/linux/dotfiles/git/.gitconfig"

  COLLISIONS=0
  run check_collisions "$REPO_DIR/linux/dotfiles" "linux"
  [ "$status" -eq 0 ]
  [ "$COLLISIONS" -eq 0 ]
}

@test "no collision: same package but different files" {
  # Both have a git package, but different files
  mkdir -p "$REPO_DIR/shared/dotfiles/git"
  echo "shared" > "$REPO_DIR/shared/dotfiles/git/.gitconfig"

  mkdir -p "$REPO_DIR/linux/dotfiles/git"
  echo "linux" > "$REPO_DIR/linux/dotfiles/git/.gitconfig_linux"

  COLLISIONS=0
  run check_collisions "$REPO_DIR/linux/dotfiles" "linux"
  [ "$status" -eq 0 ]
  [ "$COLLISIONS" -eq 0 ]
}

@test "collision: same file exists in shared and platform" {
  # Both have git/.gitconfig
  mkdir -p "$REPO_DIR/shared/dotfiles/git"
  echo "shared" > "$REPO_DIR/shared/dotfiles/git/.gitconfig"

  mkdir -p "$REPO_DIR/linux/dotfiles/git"
  echo "linux" > "$REPO_DIR/linux/dotfiles/git/.gitconfig"

  COLLISIONS=0
  check_collisions "$REPO_DIR/linux/dotfiles" "linux"
  [ "$COLLISIONS" -eq 1 ]
}

@test "collision: nested path collision" {
  # Both have zsh/.config/zsh/aliases.zsh
  mkdir -p "$REPO_DIR/shared/dotfiles/zsh/.config/zsh"
  echo "shared" > "$REPO_DIR/shared/dotfiles/zsh/.config/zsh/aliases.zsh"

  mkdir -p "$REPO_DIR/macos/dotfiles/zsh/.config/zsh"
  echo "macos" > "$REPO_DIR/macos/dotfiles/zsh/.config/zsh/aliases.zsh"

  COLLISIONS=0
  check_collisions "$REPO_DIR/macos/dotfiles" "macos"
  [ "$COLLISIONS" -eq 1 ]
}

@test "no collision: platform directory does not exist" {
  COLLISIONS=0
  run check_collisions "$REPO_DIR/nonexistent" "nonexistent"
  [ "$status" -eq 0 ]
  [ "$COLLISIONS" -eq 0 ]
}

@test "multiple collisions counted correctly" {
  mkdir -p "$REPO_DIR/shared/dotfiles/git"
  echo "s1" > "$REPO_DIR/shared/dotfiles/git/.gitconfig"

  mkdir -p "$REPO_DIR/shared/dotfiles/zsh"
  echo "s2" > "$REPO_DIR/shared/dotfiles/zsh/.zshrc"

  mkdir -p "$REPO_DIR/linux/dotfiles/git"
  echo "l1" > "$REPO_DIR/linux/dotfiles/git/.gitconfig"

  mkdir -p "$REPO_DIR/linux/dotfiles/zsh"
  echo "l2" > "$REPO_DIR/linux/dotfiles/zsh/.zshrc"

  COLLISIONS=0
  check_collisions "$REPO_DIR/linux/dotfiles" "linux"
  [ "$COLLISIONS" -eq 2 ]
}
