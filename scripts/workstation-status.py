#!/usr/bin/env python3
"""Workstation status dashboard.

Run via: uv run --with rich scripts/workstation-status.py

Checks: CLI tools, desktop apps, secrets, stow symlinks, fonts.
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
HOME = Path.home()

# ---------------------------------------------------------------------------
# Resolve workstation directory (parent of scripts/)
# ---------------------------------------------------------------------------
WORKSTATION_DIR = Path(__file__).resolve().parent.parent


def check_command(cmd: str, version_flag: str = "--version") -> tuple[bool, str]:
    """Return (installed, version_string) for a CLI tool."""
    try:
        result = subprocess.run(
            [cmd, version_flag], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            ver = (result.stdout.strip() or result.stderr.strip()).split("\n")[0]
            return True, ver
        return False, "not found"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "not installed"


def check_app(name: str, paths: list[str]) -> tuple[bool, str]:
    """Return (found, path) for a desktop app."""
    for p in paths:
        if Path(p).exists():
            return True, p
    return False, "not found"


def check_stow_links(stow_dir: Path, target: Path) -> tuple[int, int, list[str]]:
    """Check symlink health for a stow directory.

    Returns (total, healthy, broken_list).
    """
    total = 0
    healthy = 0
    broken = []
    if not stow_dir.exists():
        return 0, 0, []
    for pkg in stow_dir.iterdir():
        if not pkg.is_dir() or pkg.name.startswith("."):
            continue
        for root, _dirs, files in os.walk(pkg):
            for f in files:
                src = Path(root) / f
                rel = src.relative_to(pkg)
                dest = target / rel
                total += 1
                if dest.is_symlink() and dest.resolve().exists():
                    healthy += 1
                else:
                    broken.append(str(rel))
    return total, healthy, broken


try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()

    # -----------------------------------------------------------------------
    # System info
    # -----------------------------------------------------------------------
    console.print(
        Panel(
            f"[bold]Platform:[/bold] {platform.system()} {platform.release()}\n"
            f"[bold]Machine:[/bold] {platform.machine()}\n"
            f"[bold]Shell:[/bold] {os.environ.get('SHELL', 'unknown')}\n"
            f"[bold]Workstation:[/bold] {WORKSTATION_DIR}",
            title="System Info",
        )
    )

    # -----------------------------------------------------------------------
    # Secrets status
    # -----------------------------------------------------------------------
    age_key = HOME / ".config" / "sops" / "age" / "keys.txt"
    key_status = (
        "[green]Found[/green]" if age_key.exists() else "[red]Not found[/red]"
    )

    op_agent = (
        HOME
        / "Library"
        / "Group Containers"
        / "2BUA8C4S2C.com.1password"
        / "t"
        / "agent.sock"
        if IS_MACOS
        else HOME / ".1password" / "agent.sock"
    )
    agent_status = (
        "[green]Active[/green]"
        if op_agent.exists()
        else "[yellow]Not running[/yellow]"
    )

    console.print(
        Panel(
            f"Age key: {key_status} ({age_key})\n"
            f"1Password SSH agent: {agent_status}",
            title="Secrets",
        )
    )

    # -----------------------------------------------------------------------
    # CLI tools
    # -----------------------------------------------------------------------
    cli_table = Table(title="CLI Tools")
    cli_table.add_column("Tool", style="cyan", min_width=20)
    cli_table.add_column("Status")

    cli_tools = [
        # Git
        "git", "gh", "lazygit", "delta",
        # Shell
        "zsh", "direnv", "tmux",
        # Languages
        "node", "python3", "uv", "docker",
        # Editor / AI
        "code", "claude",
        # IaC
        "ansible-playbook", "sops", "age", "stow", "gum", "mas",
        # Modern CLI
        "bat", "rg", "fd", "fzf", "eza", "dust", "duf", "htop", "tldr", "mc",
        # Other
        "jq", "wget", "tree", "espanso",
    ]

    for tool in cli_tools:
        installed, ver = check_command(tool)
        status = f"[green]{ver}[/green]" if installed else "[red]not installed[/red]"
        cli_table.add_row(tool, status)

    console.print(cli_table)

    # -----------------------------------------------------------------------
    # Desktop apps
    # -----------------------------------------------------------------------
    app_table = Table(title="Desktop Apps")
    app_table.add_column("App", style="cyan", min_width=20)
    app_table.add_column("Status")

    if IS_MACOS:
        apps = {
            "1Password": ["/Applications/1Password.app"],
            "Firefox": ["/Applications/Firefox.app"],
            "Brave": ["/Applications/Brave Browser.app"],
            "Chrome": ["/Applications/Google Chrome.app"],
            "VS Code": ["/Applications/Visual Studio Code.app"],
            "Docker Desktop": ["/Applications/Docker.app"],
            "iTerm2": ["/Applications/iTerm.app"],
            "Slack": ["/Applications/Slack.app"],
            "Signal": ["/Applications/Signal.app"],
            "Spotify": ["/Applications/Spotify.app"],
            "VLC": ["/Applications/VLC.app"],
            "Raycast": ["/Applications/Raycast.app"],
            "Setapp": ["/Applications/Setapp.app"],
            "Dato": ["/Applications/Setapp/Dato.app"],
            "BusyCal": ["/Applications/Setapp/BusyCal.app"],
            "CleanShot X": ["/Applications/Setapp/CleanShot X.app"],
            "Downie": ["/Applications/Setapp/Downie.app"],
            "OpenIn": ["/Applications/Setapp/OpenIn.app"],
            "Paletro": ["/Applications/Setapp/Paletro.app"],
            "Stream Deck": ["/Applications/Elgato Stream Deck.app"],
            "Keka": ["/Applications/Keka.app"],
            "Backblaze": ["/Applications/Backblaze.app"],
            "Surfshark": ["/Applications/Surfshark.app"],
            "Tailscale": ["/Applications/Tailscale.app"],
            "Cyberduck": ["/Applications/Cyberduck.app"],
            "Espanso": ["/Applications/Espanso.app", "/opt/homebrew/bin/espanso"],
            "Claude": ["/Applications/Claude.app"],
        }
    else:
        apps = {
            "Firefox": ["/usr/bin/firefox", "/snap/bin/firefox"],
            "Brave": ["/usr/bin/brave-browser"],
            "Chrome": ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"],
            "VS Code": ["/usr/bin/code"],
            "Slack": ["/usr/bin/slack", "/snap/bin/slack"],
            "Signal": ["/usr/bin/signal-desktop"],
            "Spotify": ["/usr/bin/spotify", "/snap/bin/spotify"],
            "VLC": ["/usr/bin/vlc"],
            "Espanso": ["/usr/bin/espanso", str(HOME / ".local/bin/espanso")],
        }

    for name, paths in apps.items():
        found, loc = check_app(name, paths)
        status = f"[green]{loc}[/green]" if found else "[red]not found[/red]"
        app_table.add_row(name, status)

    console.print(app_table)

    # -----------------------------------------------------------------------
    # Fonts
    # -----------------------------------------------------------------------
    font_table = Table(title="Nerd Fonts")
    font_table.add_column("Font", style="cyan", min_width=20)
    font_table.add_column("Status")

    if IS_MACOS:
        font_dirs = [
            HOME / "Library" / "Fonts",
            Path("/Library/Fonts"),
        ]
    else:
        font_dirs = [HOME / ".local" / "share" / "fonts"]

    for font_name in ["JetBrainsMono", "FiraCode", "Meslo"]:
        found = False
        for fd in font_dirs:
            if fd.exists() and any(fd.rglob(f"*{font_name}*")):
                found = True
                break
        status = (
            "[green]Installed[/green]" if found else "[yellow]Not found[/yellow]"
        )
        font_table.add_row(font_name + " Nerd Font", status)

    console.print(font_table)

    # -----------------------------------------------------------------------
    # Stow symlink health
    # -----------------------------------------------------------------------
    stow_table = Table(title="Stow Symlink Health")
    stow_table.add_column("Layer", style="cyan", min_width=25)
    stow_table.add_column("Links")
    stow_table.add_column("Status")

    platform_dir = "macos" if IS_MACOS else "linux"
    stow_layers = [
        ("Shared dotfiles", WORKSTATION_DIR / "shared" / "dotfiles"),
        (
            "Shared secrets",
            WORKSTATION_DIR / "shared" / "secrets" / ".decrypted" / "dotfiles",
        ),
        (f"{platform_dir.title()} dotfiles", WORKSTATION_DIR / platform_dir / "dotfiles"),
        (
            f"{platform_dir.title()} secrets",
            WORKSTATION_DIR
            / platform_dir
            / "secrets"
            / ".decrypted"
            / "dotfiles",
        ),
    ]

    for label, stow_dir in stow_layers:
        total, healthy, broken = check_stow_links(stow_dir, HOME)
        if total == 0:
            stow_table.add_row(label, "—", "[dim]no packages[/dim]")
        elif len(broken) == 0:
            stow_table.add_row(
                label, str(total), f"[green]{healthy}/{total} OK[/green]"
            )
        else:
            stow_table.add_row(
                label,
                str(total),
                f"[red]{len(broken)} broken[/red]: {', '.join(broken[:5])}",
            )

    console.print(stow_table)

except ImportError:
    print(
        "Rich not available. Install with: uv run --with rich scripts/workstation-status.py"
    )
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Shell: {os.environ.get('SHELL', 'unknown')}")
    sys.exit(1)
