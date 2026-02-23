"""Token replacement — personalizes template config files."""

from __future__ import annotations

import logging
from pathlib import Path

from .runner import REPO_ROOT
from .state import BOOTSTRAP_SH, README_MD, SETUP_SH, SOPS_YAML, RepoConfig

logger = logging.getLogger("setup")


def replace_tokens(config: RepoConfig) -> list[str]:
    """Replace template tokens in config files. Returns list of status messages."""
    messages = []

    replacements: dict[Path, dict[str, str]] = {
        SOPS_YAML: {"${AGE_PUBLIC_KEY}": config.age_public_key},
        SETUP_SH: {"${GITHUB_REPO_URL}": config.github_repo_url},
        BOOTSTRAP_SH: {"${GITHUB_REPO_URL}": config.github_repo_url},
        README_MD: {
            "${GITHUB_REPO_URL}": config.github_repo_url,
            "${GITHUB_USERNAME}": config.github_username,
            "${REPO_NAME}": config.repo_name,
        },
    }

    for filepath, tokens in replacements.items():
        content = filepath.read_text()
        for token, value in tokens.items():
            content = content.replace(token, value)
        filepath.write_text(content)
        if filepath in (SETUP_SH, BOOTSTRAP_SH):
            filepath.chmod(0o755)
        messages.append(f"Replaced tokens in {filepath.name}")

    return messages
