SHELL := /bin/bash
PLATFORM := $(shell uname -s | tr '[:upper:]' '[:lower:]')
ifeq ($(PLATFORM),darwin)
  PLATFORM_DIR := macos
else
  PLATFORM_DIR := linux
endif

WORKSTATION_DIR ?= $(HOME)/.workstation
ANSIBLE_CONFIG := $(CURDIR)/$(PLATFORM_DIR)/ansible.cfg
export ANSIBLE_CONFIG

# SOPS looks for age keys at ~/Library/Application Support/sops/age/ on macOS,
# but we store them at ~/.config/sops/age/ (XDG convention). Tell SOPS where to look.
SOPS_AGE_KEY_FILE ?= $(HOME)/.config/sops/age/keys.txt
export SOPS_AGE_KEY_FILE

# Ensure uv and other ~/.local/bin tools are on PATH (uv installs there).
export PATH := $(HOME)/.local/bin:$(PATH)

.PHONY: help setup first-run bootstrap lint shellcheck yamllint ansible-lint \
        check-collisions test test-bats test-python check apply decrypt \
        clean-secrets status template-export \
        edit-secrets-shared edit-secrets-linux edit-secrets-macos \
        key-export key-import key-send key-receive \
        log-send log-receive

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Setup wizard (Textual TUI — replaces first-run + bootstrap)
	./setup.sh

first-run: ## One-time repo setup (age key, encrypt secrets, GitHub remote)
	./first-run.sh

bootstrap: ## Run full bootstrap for this platform (via TUI)
	./setup.sh --bootstrap

lint: ## Run all linters (yamllint, shellcheck, ansible-lint, collisions)
	./scripts/lint.sh

yamllint: ## Run yamllint on all YAML files
	yamllint . --no-warnings

shellcheck: ## Run shellcheck on all shell scripts
	shellcheck --severity=warning \
		setup.sh bootstrap.sh first-run.sh \
		linux/bootstrap.sh macos/bootstrap.sh \
		shared/lib/wizard.sh scripts/*.sh

ansible-lint: ## Run ansible-lint on all playbooks (SOPS disabled)
	ANSIBLE_VARS_ENABLED=host_group_vars ANSIBLE_CONFIG=$(CURDIR)/linux/ansible.cfg ansible-lint linux/site.yml
	ANSIBLE_VARS_ENABLED=host_group_vars ANSIBLE_CONFIG=$(CURDIR)/macos/ansible.cfg ansible-lint macos/site.yml

apply: ## Apply a specific role: make apply ROLE=git (or ROLE=gh for sub-task)
ifndef ROLE
	$(error ROLE is required. Usage: make apply ROLE=git)
endif
	./scripts/apply-role.sh $(PLATFORM_DIR) $(ROLE)

decrypt: ## Decrypt all SOPS files to .decrypted/ dirs
	@echo "Decrypting shared secrets..."
	@./scripts/decrypt-secrets.sh shared/secrets
	@echo "Decrypting $(PLATFORM_DIR) secrets..."
	@./scripts/decrypt-secrets.sh $(PLATFORM_DIR)/secrets

clean-secrets: ## Wipe decrypted secrets, unstow symlinks, truncate Ansible log
	# NOTE: rm does not securely erase data on SSDs. This is acceptable assuming
	# full-disk encryption (FileVault on macOS, LUKS on Linux) is enabled.
	# Unstow secret dotfile packages so symlinks don't dangle.
	@for secrets_dotfiles in shared/secrets/.decrypted/dotfiles $(PLATFORM_DIR)/secrets/.decrypted/dotfiles; do \
		if [ -d "$(WORKSTATION_DIR)/$$secrets_dotfiles" ]; then \
			stow -D -d "$(WORKSTATION_DIR)/$$(dirname $$secrets_dotfiles)" -t "$(HOME)" "$$(basename $$secrets_dotfiles)" 2>/dev/null || true; \
		fi; \
	done
	find . -type d -name '.decrypted' -exec rm -rf {} + 2>/dev/null || true
	# Truncate Ansible log (may contain token values from prior runs).
	@: > "$(HOME)/.local/log/ansible.log" 2>/dev/null || true
	@echo "Decrypted secrets, stow symlinks, and Ansible log cleaned."

edit-secrets-shared: ## Edit shared encrypted vars
	sops shared/secrets/vars.sops.yml

edit-secrets-linux: ## Edit Linux encrypted vars
	sops linux/secrets/vars.sops.yml

edit-secrets-macos: ## Edit macOS encrypted vars
	sops macos/secrets/vars.sops.yml

status: ## Show workstation status (stub — Rich dashboard planned)
	@uv run --with rich scripts/workstation-status.py 2>/dev/null || echo "Status dashboard requires uv + Python. Run bootstrap first."

check-collisions: ## Check for stow filename collisions between layers
	./scripts/check-stow-collisions.sh

test-bats: ## Run bats shell unit tests
	bats tests/bats/

test-python: ## Run Python unit tests (first-run wizard + setup TUI)
	uv run --with rich,pyyaml,textual,pytest,pytest-asyncio pytest tests/python/ -v

test: lint test-bats test-python ## Run all linters and tests

check: shellcheck yamllint check-collisions test-bats test-python ## Quick local verification (no ansible-lint)

key-send: ## Send age key to another machine via Magic Wormhole
	./scripts/transfer-key.sh send

key-receive: ## Receive age key from another machine via Magic Wormhole
	./scripts/transfer-key.sh receive

key-export: ## Export age key as passphrase-encrypted blob (for AirDrop/paste)
	./scripts/transfer-key.sh export

key-import: ## Import age key from passphrase-encrypted blob
	./scripts/transfer-key.sh import

log-send: ## Send bootstrap.log to another machine via Magic Wormhole
	@test -f bootstrap.log || { echo "No bootstrap.log found. Run make bootstrap first."; exit 1; }
	uv run --with magic-wormhole wormhole send bootstrap.log

log-receive: ## Receive bootstrap.log from another machine via Magic Wormhole
	uv run --with magic-wormhole wormhole receive -o bootstrap.log

template-export: ## Export clean template repo (no personal data, fresh history)
	./scripts/templatize.sh
