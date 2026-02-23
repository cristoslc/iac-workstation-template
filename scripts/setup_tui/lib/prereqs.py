"""Platform prerequisite installation — ported from bootstrap bash scripts."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from .runner import REPO_ROOT, ToolRunner

logger = logging.getLogger("setup")


def detect_platform() -> str:
    """Return 'macos' or 'linux'."""
    return "macos" if sys.platform == "darwin" else "linux"


def install_precommit(runner: ToolRunner) -> list[str]:
    """Install pre-commit and hooks. Returns status messages."""
    messages = []

    if runner.command_exists("pre-commit"):
        messages.append("pre-commit already installed.")
    else:
        messages.append("Installing pre-commit...")
        if runner.command_exists("uv"):
            runner.run(["uv", "tool", "install", "pre-commit"])
        elif runner.command_exists("pip3"):
            runner.run(["pip3", "install", "--user", "pre-commit"])
        else:
            raise RuntimeError(
                "Neither uv nor pip3 available. Cannot install pre-commit."
            )

    if not runner.command_exists("pre-commit"):
        raise RuntimeError(
            "pre-commit installation failed. Cannot continue without "
            "secret-leak protection."
        )

    git_dir = REPO_ROOT / ".git"
    if git_dir.is_dir():
        messages.append("Installing pre-commit hooks...")
        runner.run(["pre-commit", "install"], cwd=REPO_ROOT)
        hook_file = git_dir / "hooks" / "pre-commit"
        if not hook_file.exists():
            raise RuntimeError(
                "pre-commit hook not installed into .git/hooks/. Fix and re-run."
            )

    return messages


def install_bootstrap_prereqs(
    platform: str,
    *,
    on_message: callable | None = None,
) -> list[str]:
    """Install all prerequisites needed for bootstrap.

    This runs subprocesses directly (not via ToolRunner) because some
    require sudo and we want real-time output streaming.

    Returns status messages.
    """
    messages = []

    def msg(text: str) -> None:
        messages.append(text)
        logger.info(text)
        if on_message:
            on_message(text)

    if platform == "macos":
        messages.extend(_install_macos_prereqs(msg))
    else:
        messages.extend(_install_linux_prereqs(msg))

    # Ansible (via uv) — both platforms.
    if not _command_exists("ansible-playbook"):
        msg("Installing Ansible via uv...")
        _run(["uv", "tool", "install", "ansible-core"])
    else:
        msg("Ansible already installed.")

    # Ansible Galaxy collections.
    msg("Installing Ansible Galaxy collections...")
    requirements = REPO_ROOT / "shared" / "requirements.yml"
    _run(["ansible-galaxy", "collection", "install", "-r", str(requirements)])

    return messages


def _install_macos_prereqs(msg: callable) -> list[str]:
    """Install macOS-specific prerequisites."""
    messages = []

    # Homebrew prereqs (idempotent — brew skips already-installed).
    msg("Installing prerequisites via Homebrew...")
    _run(["brew", "install", "sops", "age", "stow"], check=False)

    return messages


def _install_linux_prereqs(msg: callable) -> list[str]:
    """Install Linux-specific prerequisites."""
    messages = []

    # Check which apt packages are missing.
    apt_prereqs = ["python3", "python3-venv", "curl", "stow"]
    missing = [p for p in apt_prereqs if not _dpkg_installed(p)]

    if missing:
        msg(f"Installing prerequisites: {' '.join(missing)}...")
        _run(["sudo", "apt-get", "update", "-qq"])
        _run(["sudo", "apt-get", "install", "-y", "-qq"] + missing)
    else:
        msg("APT prerequisites already installed.")

    # sops (pinned version + checksum).
    if not _command_exists("sops"):
        msg("Installing sops v3.9.4...")
        _install_sops_deb()
    else:
        msg("sops already installed.")

    # age.
    if not _command_exists("age"):
        msg("Installing age...")
        _run(["sudo", "apt-get", "install", "-y", "-qq", "age"])
    else:
        msg("age already installed.")

    return messages


def _install_sops_deb() -> None:
    """Install sops from pinned .deb with checksum verification."""
    import hashlib
    import tempfile
    import urllib.request

    version = "3.9.4"
    expected_sha256 = "e18a091c45888f82e1a7fd14561ebb913872441f92c8162d39bb63eb9308dd16"
    url = (
        f"https://github.com/getsops/sops/releases/download/"
        f"v{version}/sops_{version}_amd64.deb"
    )

    with tempfile.NamedTemporaryFile(suffix=".deb", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        _run(["curl", "-fsSL", url, "-o", tmp_path])
        actual = hashlib.sha256(Path(tmp_path).read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise RuntimeError(
                f"sops checksum mismatch! Expected: {expected_sha256}, Got: {actual}"
            )
        _run(["sudo", "dpkg", "-i", tmp_path])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _command_exists(cmd: str) -> bool:
    """Check if a command exists on PATH."""
    import shutil
    return shutil.which(cmd) is not None


def _dpkg_installed(package: str) -> bool:
    """Check if a Debian package is installed."""
    result = subprocess.run(
        ["dpkg", "-s", package],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command with logging."""
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd, capture_output=True, text=True, check=check,
        env={**os.environ, "PATH": f"{Path.home()}/.local/bin:{os.environ.get('PATH', '')}"},
    )
