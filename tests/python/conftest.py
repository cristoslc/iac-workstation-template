"""Shared fixtures for first-run.py tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add scripts/ to path so we can import first_run.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

# Import after path manipulation.
import importlib

first_run = importlib.import_module("first-run")


@pytest.fixture
def mock_runner():
    """ToolRunner with all subprocess/tool calls mocked.

    Every method that touches the outside world is a MagicMock so tests
    can assert on call counts and arguments without subprocess calls.
    """
    runner = first_run.ToolRunner(debug=True)
    ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    runner.run = MagicMock(return_value=ok)
    runner.git = MagicMock(return_value=ok)
    runner.gh = MagicMock(return_value=ok)
    runner.sops_encrypt_in_place = MagicMock()
    runner.sops_decrypt = MagicMock(return_value="")
    runner.age_keygen = MagicMock(return_value=("private-key", "age1abc"))
    runner.age_public_key_from_file = MagicMock(return_value="age1abc")
    runner.command_exists = MagicMock(return_value=True)
    return runner


@pytest.fixture
def mock_ui():
    """WizardUI with prompt/confirm/choose mocked and output captured."""
    from rich.console import Console

    console = Console(file=open("/dev/null", "w"), force_terminal=True)
    ui = first_run.WizardUI(console)

    # Track output calls for assertions.
    ui._messages: list[tuple[str, str]] = []
    original_info = ui.info
    original_warn = ui.warn
    original_error = ui.error

    def tracking_info(msg):
        ui._messages.append(("info", msg))
        original_info(msg)

    def tracking_warn(msg):
        ui._messages.append(("warn", msg))
        original_warn(msg)

    def tracking_error(msg):
        ui._messages.append(("error", msg))
        original_error(msg)

    ui.info = tracking_info
    ui.warn = tracking_warn
    ui.error = tracking_error

    # Mock interactive methods (prompt/confirm/choose).
    ui.prompt = MagicMock(return_value="")
    ui.confirm = MagicMock(return_value=False)
    ui.choose = MagicMock(return_value="")

    return ui


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a minimal repo structure with template tokens."""
    # .sops.yaml with template token.
    sops_yaml = tmp_path / ".sops.yaml"
    sops_yaml.write_text(
        "creation_rules:\n"
        "  - path_regex: '.*/secrets/.*'\n"
        "    age: '${AGE_PUBLIC_KEY}'\n"
    )

    # setup.sh with template token.
    setup_sh = tmp_path / "setup.sh"
    setup_sh.write_text(
        '#!/usr/bin/env bash\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'git clone "${GITHUB_REPO_URL}" ~/.workstation\n'
    )
    setup_sh.chmod(0o755)

    # bootstrap.sh with template token.
    bootstrap = tmp_path / "bootstrap.sh"
    bootstrap.write_text(
        '#!/usr/bin/env bash\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'git clone "${GITHUB_REPO_URL}" ~/.workstation\n'
    )
    bootstrap.chmod(0o755)

    # README.md with template tokens.
    readme = tmp_path / "README.md"
    readme.write_text(
        "# ${REPO_NAME}\n\n"
        "Clone: ${GITHUB_REPO_URL}\n"
        "By: ${GITHUB_USERNAME}\n"
    )

    # Shared secrets directory with placeholder.
    secrets_dir = tmp_path / "shared" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "vars.sops.yml").write_text("---\ngit_user_email: PLACEHOLDER\n")

    # Shell secrets file.
    shell_dir = secrets_dir / "dotfiles" / "zsh" / ".config" / "zsh"
    shell_dir.mkdir(parents=True)
    (shell_dir / "secrets.zsh.sops").write_text(
        "# Shell secrets -- sourced by .zshrc\n"
    )

    # Platform secrets.
    for plat in ["macos", "linux"]:
        plat_secrets = tmp_path / plat / "secrets"
        plat_secrets.mkdir(parents=True)
        (plat_secrets / "vars.sops.yml").write_text("---\nplaceholder: true\n")

    # .git directory (minimal).
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir()

    return tmp_path


@pytest.fixture
def sample_config():
    """A sample RepoConfig for testing."""
    return first_run.RepoConfig(
        age_public_key="age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p",
        github_username="testuser",
        repo_name="my-workstation",
    )
