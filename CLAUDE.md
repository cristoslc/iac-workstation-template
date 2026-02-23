# CLAUDE.md

## Project overview

Cross-platform (macOS + Linux) workstation provisioning using Ansible, GNU Stow, and SOPS/age for secrets management. This is a **template repo** — users fork it, run `make setup` to personalize, then bootstrap to provision. A Textual TUI (`scripts/setup_tui/`) provides the interactive wizard for both flows.

## Repo structure

- `shared/` — cross-platform roles, dotfiles, tasks, and library scripts
- `linux/`, `macos/` — platform-specific plays, roles, dotfiles, and secrets
- `scripts/setup_tui/` — Textual TUI app (screens, lib modules)
- `scripts/` — lint, decrypt, diff, transfer, and collision-check utilities
- `tests/bats/` — shell unit tests (bats-core)
- `tests/python/` — Python unit tests (first-run wizard + setup TUI)
- `setup.sh` — unified entry point (bash shim → `uv run` → Textual app)
- `first-run.sh` — legacy one-time personalization (being replaced by TUI)
- `bootstrap.sh` → `{linux,macos}/bootstrap.sh` — legacy provisioning (being replaced by TUI)

## Commit discipline

This is a personalized fork of a template repo. Personalized content (age keys, repo URLs, encrypted secrets) is mixed into the history. A future re-templatization pass will clean this up once the feature set stabilizes. Until then, just commit normally — no reordering needed.

### What is personalization?

These files contain personalized content:

| File | Personalized content |
|------|---------------------|
| `.sops.yaml` | Real age public key (replaces `${AGE_PUBLIC_KEY}`) |
| `setup.sh` | Real GitHub repo URL (replaces `${GITHUB_REPO_URL}`) |
| `bootstrap.sh` | Real GitHub repo URL (replaces `${GITHUB_REPO_URL}`) |
| `README.md` | Real repo URL, username, repo name |
| `*/secrets/*.sops.*` | Encrypted with real age key |

## Key conventions

- **SOPS bypass for lint/CI**: Set `ANSIBLE_VARS_ENABLED=host_group_vars` to disable the `community.sops.sops` vars plugin when running ansible-lint, ansible-playbook --check, or CI. Both `ansible.cfg` files enable it, but it requires an age key that won't exist in CI.
- **Shell scripts are testable**: Scripts use `BASH_SOURCE` source guards and env var overrides (`REPO_DIR`, `SHARED_DIR`) so bats-core can source them without executing main logic.
- **Pre-commit hooks**: SOPS encryption check, gitleaks, yamllint, shellcheck. The SOPS hook excludes `.sops.yaml` (the config file, not a secret).
- **Ansible module preference**: Use `ansible.builtin.unarchive` + `ansible.builtin.file: absent` instead of `shell: tar ... && rm`. Use `ansible.builtin.copy`/`apt_repository` instead of raw `.deb` downloads where apt repos are available.
- **Secrets hygiene**: `no_log: true` on any task that handles tokens/keys. Log rotation in `01-security.yml` pre_tasks. `HIST_IGNORE_SPACE` in `.zshrc`.
- **`apt_repository` must set `filename:`**: Without it, Ansible auto-generates filenames from the repo URL. If a package's own installer creates a different filename, apt sees duplicate sources. Always set `filename:` to a short stable name (e.g., `filename: docker`).
- **GPG key idempotency**: Guard download+dearmor blocks with `ansible.builtin.stat` on the keyring file. Only download when the keyring doesn't exist. If a vendor rotates their key, delete the old keyring and re-run.
- **Stale apt source cleanup**: Phase 0 pre_tasks remove conflicting apt source files using `grep -rl`, but MUST exclude the correctly-named files we manage (e.g., `vscode.list`, `1password.list`) via `case/esac`.
- **Linux Mint codename**: `lsb_release -cs` and `ansible_distribution_release` return Mint codenames (e.g., `zena`), not Ubuntu base codenames (`noble`). For apt repos that use Ubuntu codenames, read `UBUNTU_CODENAME` from `/etc/os-release` with fallback: `. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}"`.
- **Ansible roles are tool-based**: Each role (e.g., `docker`, `vpn`, `editor`) has OS-specific task files (`debian.yml`, `darwin.yml`) included from `main.yml` via `when:` conditions. Sub-tools within a role (e.g., `tailscale.yml`, `surfshark.yml` inside `vpn`) get their own task files.
- **Make target naming**: Noun-first convention (`key-send`, `log-receive`, not `send-key`, `receive-log`) so related targets group under tab completion.

## Running checks

```
make check       # fast: shellcheck, yamllint, stow collisions, bats, python tests
make lint        # full: above + ansible-lint (needs ansible-core installed)
make test        # lint + bats + python
make test-bats   # just bats tests
make test-python # just python tests (first-run + setup TUI)
```

## Common gotchas

- `.sops.yaml` is a SOPS *config* file, not an encrypted secret. Don't let hooks or patterns treat it as one.
- `bash -c 'script' arg0 arg1` — `arg0` becomes `$0`, not part of `$@`. Always use `_` as a dummy `$0` placeholder.
- `first-run.sh` must be idempotent. Guard against: existing age key, already-encrypted secrets, existing GitHub repo, SSH vs HTTPS origin URLs, empty git commits.
- `gh repo create --remote origin` sets SSH URLs. `GITHUB_REPO_URL` is HTTPS. Never compare these as strings — match on `owner/repo` instead.
- Dotfiles without shebangs (`.zshrc`, `completion.zsh`, etc.) need `# shellcheck shell=bash` directive for shellcheck pre-commit hooks.
- SOPS age key path on macOS: SOPS uses `~/Library/Application Support/` but we store at `~/.config/sops/age/keys.txt` (XDG). Every `sops` call site must set `SOPS_AGE_KEY_FILE`.
- Textual TUI logging: Never use `exec > >(tee)` — it breaks `isatty()`. Python `logging` module writes to `~/.local/log/setup.log`; Textual widgets handle console display.
