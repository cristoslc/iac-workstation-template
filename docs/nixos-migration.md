# NixOS Migration Path

This repo is structured to accommodate a future NixOS migration.

## How It Maps

| Current | NixOS Equivalent |
|---|---|
| `linux/` directory | `nixos/` directory |
| Ansible roles | Nix modules or Home Manager programs |
| `site.yml` playbook | `configuration.nix` |
| Stow dotfiles | Home Manager `home.file` or `xdg.configFile` |
| Brewfile | `environment.systemPackages` |
| `bootstrap.sh` | `nixos-rebuild switch` |
| SOPS + age | `sops-nix` (native NixOS integration) |

## Migration Strategy

1. Add a `nixos/` directory alongside `linux/` and `macos/`
2. Migrate one role at a time to a Nix module
3. Dotfiles transfer as-is (Home Manager can consume the same files)
4. `sops-nix` provides native SOPS integration for NixOS
5. Keep the Ansible setup functional during migration for fallback

## When to Migrate

- Wayland support matures for Espanso and Vicinae
- Workload and tooling stabilize
- Comfort level with Nix ecosystem increases
- Ubuntu 24.04 LTS support window (through 2029) provides a long runway
