"""Secret field definitions and collection logic."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .encryption import write_and_encrypt
from .runner import REPO_ROOT, ToolRunner

logger = logging.getLogger("setup")


@dataclass
class SecretField:
    """One secret the system consumes."""

    key: str              # Variable name (git_user_email, ANTHROPIC_API_KEY, ...)
    label: str            # Human-readable label for the prompt
    placeholder: str      # Example value shown in empty field
    description: str      # What this secret is used for
    used_by: str          # Which roles/tools consume this secret
    doc_url: str = ""     # URL to docs on how to obtain this secret
    password: bool = False  # Mask input


# Ansible vars -- written to vars.sops.yml as YAML key/value pairs.
SHARED_ANSIBLE_VARS: list[SecretField] = [
    SecretField(
        key="git_user_email",
        label="Git email",
        placeholder="you@example.com",
        description="Sets git config user.email globally",
        used_by="git role",
    ),
    SecretField(
        key="git_user_name",
        label="Git display name",
        placeholder="Your Name",
        description="Sets git config user.name globally",
        used_by="git role",
    ),
    SecretField(
        key="git_signing_key",
        label="SSH signing key (public)",
        placeholder="ssh-ed25519 AAAA...",
        description="1Password SSH public key for commit signing",
        used_by="git role",
    ),
]

# Shell secrets -- written to secrets.zsh.sops as export statements.
SHELL_SECRETS: list[SecretField] = [
    SecretField(
        key="ANTHROPIC_API_KEY",
        label="Anthropic API key",
        placeholder="sk-ant-...",
        description="API access for Claude CLI and SDK",
        used_by="claude-code role, Claude CLI",
        doc_url="https://console.anthropic.com/settings/keys",
        password=True,
    ),
    SecretField(
        key="HOMEBREW_GITHUB_API_TOKEN",
        label="GitHub token for Homebrew",
        placeholder="ghp_...",
        description="Avoids GitHub API rate limits during brew install",
        used_by="homebrew role (macOS)",
        doc_url="https://github.com/settings/tokens",
        password=True,
    ),
]


def mask_value(value: str) -> str:
    """Show first 4 and last 4 chars of a secret for confirmation."""
    if len(value) <= 10:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def load_existing_ansible_vars(runner: ToolRunner) -> dict[str, str]:
    """Load current values from vars.sops.yml for pre-filling prompts."""
    shared_vars = REPO_ROOT / "shared" / "secrets" / "vars.sops.yml"
    current: dict[str, str] = {}
    if shared_vars.exists():
        decrypted = runner.sops_decrypt(shared_vars)
        for line in decrypted.splitlines():
            if ":" in line and not line.startswith("#") and not line.startswith("---"):
                key, _, val = line.partition(":")
                val = val.strip().strip("'\"")
                if val and val != "PLACEHOLDER":
                    current[key.strip()] = val
    return current


def load_existing_shell_exports(runner: ToolRunner) -> dict[str, str]:
    """Load current export values from secrets.zsh.sops."""
    shell_file = (
        REPO_ROOT / "shared" / "secrets" / "dotfiles" / "zsh"
        / ".config" / "zsh" / "secrets.zsh.sops"
    )
    existing: dict[str, str] = {}
    if shell_file.exists():
        content = runner.sops_decrypt(shell_file)
        if content:
            for line in content.splitlines():
                if line.startswith("export "):
                    eq_pos = line.find("=")
                    if eq_pos > 0:
                        ekey = line[len("export "):eq_pos]
                        eval_ = line[eq_pos + 1:].strip().strip('"')
                        existing[ekey] = eval_
    return existing


def save_ansible_vars(
    runner: ToolRunner, collected: dict[str, str]
) -> None:
    """Write vars.sops.yml with collected values."""
    shared_vars = REPO_ROOT / "shared" / "secrets" / "vars.sops.yml"
    yaml_lines = ["---"]
    for key, value in collected.items():
        yaml_lines.append(f'{key}: "{value}"')
    write_and_encrypt(runner, shared_vars, "\n".join(yaml_lines))


def save_shell_exports(
    runner: ToolRunner, collected: dict[str, str]
) -> None:
    """Write secrets.zsh.sops with collected export values."""
    shell_file = (
        REPO_ROOT / "shared" / "secrets" / "dotfiles" / "zsh"
        / ".config" / "zsh" / "secrets.zsh.sops"
    )
    if collected:
        lines = ["# Shell secrets -- sourced by .zshrc"]
        for ekey, eval_ in collected.items():
            lines.append(f'export {ekey}="{eval_}"')
        write_and_encrypt(runner, shell_file, "\n".join(lines))
