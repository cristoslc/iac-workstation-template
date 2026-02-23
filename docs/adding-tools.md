# Adding a New Tool

## Find the Right Role

Roles are organized by **function** (capability), not by tool name. Before creating anything new, check if an existing role already covers the category:

| If you're adding... | It belongs in... |
|---|---|
| A browser | `shared/roles/browsers` |
| A git-related CLI tool | `shared/roles/git` |
| A shell plugin or shell tool | `shared/roles/shell` |
| A terminal emulator or multiplexer | `shared/roles/terminal` |
| A code editor or IDE | `shared/roles/editor` |
| A chat or messaging app | `shared/roles/communication` |
| A music/video player | `shared/roles/media` |
| A VPN or network overlay | `shared/roles/vpn` |
| A backup tool | `shared/roles/backups` |
| An app launcher | `shared/roles/launchers` |
| A text expansion tool | `shared/roles/text-expansion` |
| An SFTP/file transfer client | `shared/roles/file-transfer` |
| An archive/compression utility | `shared/roles/utilities` |
| A calendar or date/time app | `shared/roles/calendar` |
| A screenshot or screen capture tool | `shared/roles/screenshots` |
| A link/file routing handler | `shared/roles/link-handler` |
| Stream Deck companion software | `shared/roles/stream-deck` |

## Add a Sub-Task to an Existing Role

Example: adding **tig** (git TUI) to the `git` role.

1. Create the sub-task file with platform guards:
   ```yaml
   # shared/roles/git/tasks/tig.yml
   - name: Install tig (macOS)
     when: ansible_os_family == "Darwin"
     community.general.homebrew:
       name: tig
       state: present

   - name: Install tig (Debian)
     when: ansible_os_family == "Debian"
     ansible.builtin.apt:
       name: tig
       state: present
     become: true
   ```

2. Include it from the role's `main.yml` with a tool-level tag:
   ```yaml
   # shared/roles/git/tasks/main.yml (append)
   - name: Install tig
     ansible.builtin.include_tasks: tig.yml
     tags: [tig]
   ```

3. Add the tool tag to the playbook role entry:
   ```yaml
   # Both plays/02-dev-tools.yml
   - role: git
     tags: [git, gh, lazygit, delta, tig, dev-tools]
   ```

4. Add to the Brewfile (macOS):
   ```ruby
   # --- Git (role: git) ---
   brew "tig"
   ```

Now `make apply ROLE=git` runs everything, `make apply ROLE=tig` runs only tig.

## Create a New Cross-Platform Role

Only create a new role when no existing role covers the capability.

1. Create the role structure:
   ```
   shared/roles/<name>/
   ├── tasks/
   │   ├── main.yml       # OS dispatch or sub-task includes
   │   ├── darwin.yml      # macOS install/verify
   │   └── debian.yml      # Linux install
   └── defaults/
       └── main.yml        # Default variables (if needed)
   ```

2. Follow naming conventions:
   - **Plural** if the role manages multiple tools of the same type (`browsers`, `launchers`)
   - **Singular** if one tool or one concept (`editor`, `terminal`)

3. Add to the appropriate phase playbook in **both** platforms:
   ```yaml
   # linux/plays/03-desktop.yml AND macos/plays/03-desktop.yml
   - role: <name>
     tags: [<name>, <tool1>, <tool2>, desktop]
   ```

4. If it has config files, create a stow package:
   ```
   shared/dotfiles/<tool>/.config/<tool>/config.yml
   ```

5. Add to the Brewfile with a role comment:
   ```ruby
   # --- <Name> (role: <name>) ---
   cask "<tool>"
   ```

## Add a Setapp-Managed App (macOS only)

Setapp apps can't be installed via `brew bundle` — they require the Setapp desktop app. Roles verify their presence and emit a reminder if missing.

1. Add a stat check to the role's `darwin.yml`:
   ```yaml
   - name: Check if MyApp is installed
     ansible.builtin.stat:
       path: /Applications/Setapp/MyApp.app
     register: myapp_check

   - name: Remind to install MyApp via Setapp
     when: not myapp_check.stat.exists
     ansible.builtin.debug:
       msg: "MyApp is not installed. Install it via Setapp."
   ```

2. Add a Setapp comment in the Brewfile under the role's section:
   ```ruby
   # --- MyRole (role: my-role) ---
   # MyApp (Setapp)
   ```

3. Add a post-install step in `docs/post-install.md` under macOS.

4. The Setapp cask itself is in the Brewfile and installs the Setapp app manager. Individual Setapp apps are then installed manually through its UI.

## Dotfile Conventions

- **Stow packages** are auto-discovered by directory name — don't need to match role names.
- **Zsh fragments** in `~/.config/zsh/`: shared = generic (`aliases.zsh`), platform = platform name (`linux.zsh`), secrets = `secrets.zsh`, local = `local.zsh`.
- Config files go under `~/.config/<tool>/` per XDG convention.
- **Tags**: function role name for the whole role, tool name for individual sub-tasks.
