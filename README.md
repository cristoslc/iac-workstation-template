# iac-daily-driver-environments

IaC-driven setup that makes Linux and macOS dev workstations fungible. Run `./bootstrap.sh` on a fresh install or an existing system and get a fully configured development environment.

- **Linux**: Mint 22 / Cinnamon / X11
- **macOS**: Homebrew + Raycast + opinionated defaults

## First Run

One-time setup to personalize the template and push to your own repo.

```bash
git clone https://github.com/TEMPLATE_OWNER/iac-daily-driver-environments.git ~/.workstation
cd ~/.workstation
./first-run.sh
```

The script self-installs its prerequisites (`age`, `sops`, `gum`, `gh`, `envsubst`, `pre-commit`) and walks you through:

1. **Generate age keypair** — creates `~/.config/sops/age/keys.txt`
2. **GitHub username + repo name** — personalizes clone URLs and config
3. **Encrypt secrets** — encrypts all placeholder secret files with your age key
4. **Pre-commit hooks** — installs the SOPS encryption check
5. **Create your GitHub repo** — via `gh repo create`, pushes initial commit
6. **Edit secrets** — guided walk-through to populate each secret file with real values

After first-run, the repo is yours. All subsequent machines clone from your repo.

## Quick Start

For bootstrapping a **second machine** from your own repo:

```bash
# Copy your age key to the new machine first
mkdir -p ~/.config/sops/age
# (paste or copy keys.txt into place)
chmod 600 ~/.config/sops/age/keys.txt

# Clone and bootstrap
git clone ${GITHUB_REPO_URL} ~/.workstation
cd ~/.workstation
./bootstrap.sh
```

The bootstrap wizard (powered by [gum](https://github.com/charmbracelet/gum)) walks you through:

1. **System type** — fresh install, existing system + new account, or existing system + existing account
2. **Role groups** — which phases to apply (system, security, dev tools, desktop, dotfiles)
3. **Confirmation** — summary of what will happen before Ansible runs

### Selective Runs

```bash
make apply ROLE=git             # Apply git + gh + lazygit + delta
make apply ROLE=gh              # Apply just the gh sub-task
make apply ROLE=browsers        # Apply all browsers + set daily driver
make apply ROLE=secrets-manager # Apply 1Password + SOPS
make apply ROLE=shell           # Apply zsh + direnv
make apply ROLE=fonts           # Install Nerd Fonts
make apply ROLE=file-transfer   # Apply Cyberduck/Filezilla
make apply ROLE=text-expansion  # Apply Espanso
make apply ROLE=firewall        # Apply firewall rules (ufw / socketfilterfw)
make lint                       # Run ansible-lint + yamllint
make decrypt                    # Decrypt SOPS files to .decrypted/ (debugging)
make clean-secrets              # Wipe decrypted secrets + dangling symlinks
make status                     # Workstation status dashboard
make check-collisions           # Verify no stow filename conflicts
```

## Architecture

```
├── bootstrap.sh              OS dispatcher → platform bootstrap
├── Makefile                  Developer ergonomics (apply, lint, decrypt, status)
├── .sops.yaml                SOPS creation rules (age encryption)
├── .editorconfig             Editor formatting rules
├── shared/
│   ├── lib/wizard.sh         gum TUI wizard (sourced by both platforms)
│   ├── requirements.yml      Ansible Galaxy collections
│   ├── tasks/                Reusable task includes (version-check, download-verify)
│   ├── roles/                Function-based cross-platform roles
│   │   ├── git/              git + gh + lazygit + delta + commit signing
│   │   ├── shell/            zsh + direnv
│   │   ├── secrets-manager/  1Password (+ SSH agent) + SOPS/age
│   │   ├── terminal/         tmux + iTerm2 verification
│   │   ├── editor/           VS Code + extensions + settings
│   │   ├── firewall/          ufw (Linux) + socketfilterfw (macOS)
│   │   ├── fonts/            JetBrains Mono, Fira Code, Meslo (Nerd Fonts)
│   │   ├── browsers/         Firefox + Brave + Chrome, daily driver default
│   │   ├── launchers/        Raycast (macOS) / Vicinae (Linux)
│   │   ├── calendar/         Dato + BusyCal (Setapp)
│   │   ├── communication/    Slack + Signal
│   │   ├── media/            Spotify + VLC + Downie (Setapp)
│   │   ├── vpn/              Tailscale + Surfshark
│   │   ├── backups/          Backblaze (macOS) / Timeshift (Linux)
│   │   ├── screenshots/      CleanShot X (Setapp) / placeholder (Linux)
│   │   ├── link-handler/     OpenIn (Setapp) / xdg-mime (Linux)
│   │   ├── stream-deck/      Elgato (macOS) / OpenDeck (Linux)
│   │   ├── text-expansion/   Espanso (both platforms)
│   │   ├── utilities/        Keka (macOS) / p7zip + unrar (Linux)
│   │   ├── file-transfer/    Cyberduck (macOS) / Filezilla (Linux)
│   │   ├── python/           uv + global tools
│   │   ├── node/             fnm + LTS
│   │   ├── docker/           Docker Engine/Desktop
│   │   ├── claude-code/      Claude Code CLI
│   │   └── stow/             GNU Stow dotfile deployment
│   ├── dotfiles/             Cross-platform stow packages (zsh, git, tmux, ssh, direnv, ...)
│   └── secrets/              Encrypted shared vars + secret dotfiles
├── linux/
│   ├── bootstrap.sh          Linux entry point (apt prereqs → uv → Ansible)
│   ├── site.yml → plays/     Phase playbooks (security → dev → desktop → dotfiles)
│   ├── roles/                Linux-only roles (base, system, desktop-env, dev)
│   ├── dotfiles/             Linux stow packages (ssh, zsh, git, espanso, vscode)
│   └── secrets/              Encrypted Linux vars + secret dotfiles
├── macos/
│   ├── bootstrap.sh          macOS entry point (Homebrew → uv → Ansible)
│   ├── site.yml → plays/     Phase playbooks
│   ├── roles/                macOS-only roles (homebrew, mas, macos-defaults)
│   ├── dotfiles/             macOS stow packages (ssh, zsh, git, vscode, iterm2)
│   └── secrets/              Encrypted macOS vars
├── docs/                     Detailed documentation
└── scripts/                  Linting, collision checks, status dashboard
```

### Role Organization

Roles are organized by **function** (what capability they provide), not by tool name. Each role handles both platforms internally via OS dispatch. This ensures:

- Adding a tool on macOS naturally prompts considering the Linux equivalent
- `make apply ROLE=<function>` runs everything related to that capability
- Sub-task tags allow running individual tools: `make apply ROLE=gh` runs only the gh sub-task within the git role

**Naming convention**: plural when multiple tools of the same type (`browsers`, `launchers`, `backups`), singular when one tool or concept (`git`, `shell`, `terminal`, `editor`).

### How the Layers Work

**Ansible** installs tools and configures the system. Shared roles use OS dispatch (`include_tasks: debian.yml` / `darwin.yml`). Platform roles handle OS-specific tools.

**GNU Stow** (`--no-folding`) manages dotfiles as file-level symlinks. Four layers, stowed in order:

1. `shared/dotfiles/` — cross-platform base
2. `shared/secrets/dotfiles/` — decrypted shared secrets
3. `<platform>/dotfiles/` — platform-specific
4. `<platform>/secrets/dotfiles/` — decrypted platform secrets

Collisions between layers are prevented by naming convention (not numeric prefixes):

| Layer | Example filename |
|---|---|
| Shared | `aliases.zsh`, `functions.zsh` |
| Platform | `linux.zsh`, `macos.zsh` |
| Secrets | `secrets.zsh` |
| Local (user, gitignored) | `local.zsh` |

### Composable Dotfiles

Every repo-managed config supports a local override file that is **never tracked by git**:

- `~/.config/zsh/local.zsh` — machine-specific shell config
- `~/.config/git/local.gitconfig` — machine-specific git settings (user.email, signing key)
- `~/.config/espanso/match/local.yml` — machine-specific text expansions

On existing systems, bootstrap backs up pre-existing dotfiles to `~/.workstation-backup/<timestamp>/` and migrates their content into the appropriate local override file.

### Git Commit Signing

Commits are signed via 1Password SSH keys. The shared `.gitconfig` enables `gpg.format = ssh` and `commit.gpgsign = true`. Platform-specific gitconfigs (stowed automatically) point `gpg.ssh.program` to the correct `op-ssh-sign` binary:

- **macOS**: `/Applications/1Password.app/Contents/MacOS/op-ssh-sign`
- **Linux**: `/opt/1Password/op-ssh-sign`

Your `local.gitconfig` provides `user.name`, `user.email`, and `user.signingKey` (your 1Password SSH key fingerprint).

### Setapp Integration

Several macOS desktop apps are managed through [Setapp](https://setapp.com). These install to `/Applications/Setapp/` and can't be automated — each role uses a `stat` check to verify presence and emits a reminder if the app is missing. Managed apps: Dato, BusyCal, CleanShot X, Downie, OpenIn, Paletro.

### Bootstrap Modes

| Mode | System roles | Dotfiles | macOS defaults |
|---|---|---|---|
| Fresh install | Apply all | Replace everything | Apply unconditionally |
| Existing system, new account | Skip (system already configured) | Apply normally | Diff and confirm per category |
| Existing system, existing account | Skip unless opted in | Back up existing, migrate to local overrides | Diff and confirm per category |

## Secrets

All secrets encrypted with [SOPS](https://github.com/getsops/sops) + [age](https://github.com/FiloSottile/age). The repo is public.

```bash
make edit-secrets-shared      # Edit shared encrypted vars
make edit-secrets-linux       # Edit Linux encrypted vars
make edit-secrets-macos       # Edit macOS encrypted vars
make decrypt                  # Decrypt to .decrypted/ (for debugging)
make clean-secrets            # Wipe decrypted files, unstow symlinks, truncate Ansible log
```

Two pre-commit hooks protect against committing secrets: a SOPS MAC check verifies all `*.sops.*` files are encrypted, and [gitleaks](https://github.com/gitleaks/gitleaks) scans all staged files for hardcoded tokens, keys, and credentials.

See [docs/secrets.md](docs/secrets.md) for setup, key distribution, and rotation.

## Tools Managed

### Phase 1 — Security
`secrets-manager`: 1Password (+ SSH agent + commit signing), SOPS + age · `firewall`: ufw deny-incoming (Linux), socketfilterfw + stealth mode (macOS)

### Phase 2 — Development
`git`: git, gh, lazygit, delta · `shell`: zsh, direnv · `python`: uv · `node`: fnm · `docker`: Docker Engine/Desktop · `editor`: VS Code + settings · `claude-code`: Claude Code CLI · `fonts`: JetBrains Mono, Fira Code, Meslo (Nerd Fonts) · `terminal`: tmux, iTerm2

### Phase 3 — Desktop
`browsers`: Firefox, Brave, Chrome · `launchers`: Raycast / Vicinae · `text-expansion`: Espanso · `calendar`: Dato, BusyCal (Setapp) · `communication`: Slack, Signal · `media`: Spotify, VLC, Downie (Setapp) · `screenshots`: CleanShot X (Setapp) · `link-handler`: OpenIn (Setapp) / xdg-mime · `stream-deck`: Elgato / OpenDeck · `vpn`: Tailscale, Surfshark · `backups`: Backblaze / Timeshift · `utilities`: Keka / p7zip · `file-transfer`: Cyberduck / Filezilla

### Platform-only
**Linux**: `base` (build-essential, ripgrep, fd, bat, fzf, dust, duf, ...) · `system` (X11 check, release pin) · `desktop-env` (Cinnamon keybindings) · `dev` (gcc, pkg-config, headers)
**macOS**: `homebrew` (Brewfile) · `mas` (App Store: Amphetamine) · `macos-defaults` (Dock, Finder, keyboard, trackpad, screenshots)

## Documentation

- [Post-install manual steps](docs/post-install.md) — things that can't be automated
- [Adding a new tool](docs/adding-tools.md) — how to add roles and dotfiles
- [Secrets management](docs/secrets.md) — SOPS + age setup, workflow, rotation
- [Vicinae fallback](docs/fallback.md) — swap to Ulauncher + CopyQ if needed
- [NixOS migration](docs/nixos-migration.md) — future migration path

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| IaC tool | Ansible | Cross-platform, declarative roles, large ecosystem |
| Dotfiles | GNU Stow | Simple, no magic, file-level symlinks with `--no-folding` |
| Secrets | SOPS + age | Public repo safe, no GPG complexity, Ansible integration |
| Commit signing | 1Password SSH | No GPG key management, keys already in 1Password |
| Role organization | Function-based | Each role = one capability, handles both platforms internally |
| Shell | zsh | Default on macOS, widely supported on Linux |
| Python | uv | Fast, replaces pip + pyenv + virtualenv |
| Node | fnm | Fast, rust-based, cross-platform |
| Bootstrap UX | gum | Single binary, no dependencies, beautiful TUI |
| Ansible install | uv tool install | Avoids stale distro packages |
| Supply chain | Pinned versions + SHA-256 checksums | All binary downloads verified via `download-and-verify.yml`; apt repos use GPG keys |
| Secret scanning | gitleaks + SOPS MAC check | Two-layer pre-commit: pattern-based scanner + encryption verification |
| Audit logging | Ansible log with rotation | `~/.local/log/ansible.log`, rotated per run, `no_log` on sensitive tasks |
