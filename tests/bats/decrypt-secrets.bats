#!/usr/bin/env bats

load helpers/setup

SCRIPT_DIR="$(cd "$(dirname "${BATS_TEST_FILENAME}")/../.." && pwd)"

setup() {
  TEST_TEMP="$(mktemp -d)"
  export TEST_TEMP

  # Source the script (loads compute_output_path function)
  source "$SCRIPT_DIR/scripts/decrypt-secrets.sh"
}

teardown() {
  rm -rf "$TEST_TEMP"
}

@test "compute_output_path: .sops.yml → .yml" {
  result="$(compute_output_path "/out" "vars.sops.yml")"
  [ "$result" = "/out/vars.yml" ]
}

@test "compute_output_path: .sops.yaml → .yaml" {
  result="$(compute_output_path "/out" "config.sops.yaml")"
  [ "$result" = "/out/config.yaml" ]
}

@test "compute_output_path: .sops → strip extension" {
  result="$(compute_output_path "/out" "secrets.zsh.sops")"
  [ "$result" = "/out/secrets.zsh" ]
}

@test "compute_output_path: bare .sops → no extension" {
  result="$(compute_output_path "/out" "keyfile.sops")"
  [ "$result" = "/out/keyfile" ]
}

@test "compute_output_path: nested path preserved" {
  result="$(compute_output_path "/out" "dotfiles/zsh/.config/zsh/secrets.zsh.sops")"
  [ "$result" = "/out/dotfiles/zsh/.config/zsh/secrets.zsh" ]
}

@test "compute_output_path: nested .sops.yml path preserved" {
  result="$(compute_output_path "/out" "some/deep/path/vars.sops.yml")"
  [ "$result" = "/out/some/deep/path/vars.yml" ]
}
