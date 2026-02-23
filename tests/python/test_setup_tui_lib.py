"""Tests for setup_tui.lib modules — the new UI-decoupled business logic."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Add scripts/ to path so setup_tui package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from setup_tui.lib.runner import REPO_ROOT, ToolRunner
from setup_tui.lib.state import (
    AGE_KEY_PATH,
    AGE_TOKEN,
    RepoConfig,
    ResumeState,
    detect_resume_state,
    extract_resume_config,
)
from setup_tui.lib.age import AgeKeyError, generate_or_load_age_key
from setup_tui.lib.tokens import replace_tokens
from setup_tui.lib.encryption import EncryptionError, encrypt_secret_files, write_and_encrypt
from setup_tui.lib.git_ops import (
    GitError,
    GitHubError,
    commit_and_push,
    create_github_repo,
    detach_from_template,
    remove_origin,
)
from setup_tui.lib.secrets import (
    SHARED_ANSIBLE_VARS,
    SHELL_SECRETS,
    SecretField,
    mask_value,
    load_existing_ansible_vars,
    load_existing_shell_exports,
    save_ansible_vars,
    save_shell_exports,
)
from setup_tui.lib.prereqs import detect_platform, install_precommit
from setup_tui.lib.setup_logging import LOG_DIR, LOG_FILE, setup_logging


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_runner():
    """ToolRunner with all subprocess/tool calls mocked."""
    runner = ToolRunner(debug=True)
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
def sample_config():
    """A sample RepoConfig for testing."""
    return RepoConfig(
        age_public_key="age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p",
        github_username="testuser",
        repo_name="my-workstation",
    )


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a minimal repo structure with template tokens."""
    sops_yaml = tmp_path / ".sops.yaml"
    sops_yaml.write_text(
        "creation_rules:\n"
        "  - path_regex: '.*/secrets/.*'\n"
        "    age: '${AGE_PUBLIC_KEY}'\n"
    )

    setup_sh = tmp_path / "setup.sh"
    setup_sh.write_text(
        '#!/usr/bin/env bash\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'git clone "${GITHUB_REPO_URL}" ~/.workstation\n'
    )
    setup_sh.chmod(0o755)

    bootstrap_sh = tmp_path / "bootstrap.sh"
    bootstrap_sh.write_text(
        '#!/usr/bin/env bash\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'git clone "${GITHUB_REPO_URL}" ~/.workstation\n'
    )
    bootstrap_sh.chmod(0o755)

    readme = tmp_path / "README.md"
    readme.write_text(
        "# ${REPO_NAME}\n\n"
        "Clone: ${GITHUB_REPO_URL}\n"
        "By: ${GITHUB_USERNAME}\n"
    )

    secrets_dir = tmp_path / "shared" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "vars.sops.yml").write_text("---\ngit_user_email: PLACEHOLDER\n")

    shell_dir = secrets_dir / "dotfiles" / "zsh" / ".config" / "zsh"
    shell_dir.mkdir(parents=True)
    (shell_dir / "secrets.zsh.sops").write_text(
        "# Shell secrets -- sourced by .zshrc\n"
    )

    for plat in ["macos", "linux"]:
        plat_secrets = tmp_path / plat / "secrets"
        plat_secrets.mkdir(parents=True)
        (plat_secrets / "vars.sops.yml").write_text("---\nplaceholder: true\n")

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "hooks").mkdir()

    return tmp_path


# ===========================================================================
# SetupApp (app.py)
# ===========================================================================

class TestSetupApp:
    """Tests for the main Textual app — instantiation only (no UI rendering)."""

    def test_instantiation(self):
        """SetupApp must not collide with Textual's debug property."""
        from setup_tui.app import SetupApp
        app = SetupApp(debug=False)
        assert app._debug_mode is False
        assert isinstance(app.runner, ToolRunner)

    def test_debug_mode_flag(self):
        from setup_tui.app import SetupApp
        app = SetupApp(debug=True)
        assert app._debug_mode is True
        assert app.runner.debug is True

    def test_platform_detection(self):
        from setup_tui.app import SetupApp
        app = SetupApp()
        assert app.platform in ("macos", "linux")

    def test_sops_env_var_set(self):
        import os
        from setup_tui.app import SetupApp
        SetupApp()
        assert os.environ.get("SOPS_AGE_KEY_FILE") == str(AGE_KEY_PATH)


# ===========================================================================
# Pure functions
# ===========================================================================

class TestMaskValue:
    def test_short_values_fully_masked(self):
        assert mask_value("abc") == "***"
        assert mask_value("1234567890") == "**********"

    def test_long_values_show_ends(self):
        result = mask_value("sk-ant-abcdef12345xyz")
        assert result.startswith("sk-a")
        assert result.endswith("5xyz")
        assert "*" in result
        assert len(result) == len("sk-ant-abcdef12345xyz")

    def test_empty_string(self):
        assert mask_value("") == ""

    def test_boundary_length_11(self):
        """Exactly 11 chars: should show first 4 + last 4 with 3 stars."""
        result = mask_value("12345678901")
        assert result == "1234***8901"


class TestDetectPlatform:
    def test_returns_known_platform(self):
        result = detect_platform()
        assert result in ("macos", "linux")


class TestRepoConfig:
    def test_github_repo_url(self, sample_config):
        assert sample_config.github_repo_url == (
            "https://github.com/testuser/my-workstation.git"
        )

    def test_default_values(self):
        config = RepoConfig()
        assert config.age_public_key == ""
        assert config.github_username == ""
        assert config.repo_name == ""
        assert config.github_repo_url == "https://github.com//.git"

    def test_url_with_special_chars_in_name(self):
        config = RepoConfig(github_username="user", repo_name="my-repo-2025")
        assert config.github_repo_url == "https://github.com/user/my-repo-2025.git"


class TestResumeState:
    def test_defaults(self):
        state = ResumeState()
        assert state.is_personalized is False
        assert state.has_origin is False
        assert state.has_commit is False
        assert state.is_pushed is False
        assert state.has_precommit is False
        assert state.has_placeholder_secrets is False
        assert state.pending == []

    def test_pending_is_mutable_default(self):
        """Each instance should get its own pending list."""
        s1 = ResumeState()
        s2 = ResumeState()
        s1.pending.append("task")
        assert s2.pending == []


class TestSecretFieldDeclarations:
    def test_shell_secrets_have_doc_urls(self):
        for sf in SHELL_SECRETS:
            assert sf.doc_url, f"{sf.key} should have a doc_url"
            assert sf.doc_url.startswith("https://")

    def test_all_fields_have_used_by(self):
        for sf in SHARED_ANSIBLE_VARS + SHELL_SECRETS:
            assert sf.used_by, f"{sf.key} should have a used_by"

    def test_ansible_vars_not_password(self):
        """Ansible vars (git email, name) should not be masked."""
        for sf in SHARED_ANSIBLE_VARS:
            assert sf.password is False

    def test_shell_secrets_are_passwords(self):
        """Shell secrets (API keys) should be masked."""
        for sf in SHELL_SECRETS:
            assert sf.password is True, f"{sf.key} should have password=True"

    def test_unique_keys(self):
        """All secret field keys must be unique."""
        all_keys = [sf.key for sf in SHARED_ANSIBLE_VARS + SHELL_SECRETS]
        assert len(all_keys) == len(set(all_keys))


class TestAgeToken:
    def test_token_value(self):
        assert AGE_TOKEN == "${AGE_PUBLIC_KEY}"


# ===========================================================================
# Token replacement (no `ui` param, returns messages)
# ===========================================================================

class TestReplaceTokens:
    def test_substitutes_age_key(self, tmp_repo, sample_config, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.tokens.SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr("setup_tui.lib.tokens.SETUP_SH", tmp_repo / "setup.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.README_MD", tmp_repo / "README.md")

        msgs = replace_tokens(sample_config)

        content = (tmp_repo / ".sops.yaml").read_text()
        assert "${AGE_PUBLIC_KEY}" not in content
        assert sample_config.age_public_key in content
        assert len(msgs) == 4  # one per file

    def test_substitutes_readme_tokens(self, tmp_repo, sample_config, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.tokens.SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr("setup_tui.lib.tokens.SETUP_SH", tmp_repo / "setup.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.README_MD", tmp_repo / "README.md")

        replace_tokens(sample_config)

        content = (tmp_repo / "README.md").read_text()
        assert "${GITHUB_REPO_URL}" not in content
        assert "${GITHUB_USERNAME}" not in content
        assert "${REPO_NAME}" not in content
        assert sample_config.github_username in content
        assert sample_config.repo_name in content

    def test_preserves_bash_variables(self, tmp_repo, sample_config, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.tokens.SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr("setup_tui.lib.tokens.SETUP_SH", tmp_repo / "setup.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.README_MD", tmp_repo / "README.md")

        replace_tokens(sample_config)

        content = (tmp_repo / "setup.sh").read_text()
        assert "${BASH_SOURCE[0]}" in content

    def test_setup_sh_executable_after_replacement(
        self, tmp_repo, sample_config, monkeypatch
    ):
        monkeypatch.setattr("setup_tui.lib.tokens.SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr("setup_tui.lib.tokens.SETUP_SH", tmp_repo / "setup.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.README_MD", tmp_repo / "README.md")

        replace_tokens(sample_config)

        mode = (tmp_repo / "setup.sh").stat().st_mode
        assert mode & 0o755 == 0o755

    def test_substitutes_bootstrap_sh_url(
        self, tmp_repo, sample_config, monkeypatch
    ):
        monkeypatch.setattr("setup_tui.lib.tokens.SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr("setup_tui.lib.tokens.SETUP_SH", tmp_repo / "setup.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.README_MD", tmp_repo / "README.md")

        replace_tokens(sample_config)

        content = (tmp_repo / "bootstrap.sh").read_text()
        assert "${GITHUB_REPO_URL}" not in content
        assert sample_config.github_repo_url in content
        mode = (tmp_repo / "bootstrap.sh").stat().st_mode
        assert mode & 0o755 == 0o755

    def test_returns_status_messages(self, tmp_repo, sample_config, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.tokens.SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr("setup_tui.lib.tokens.SETUP_SH", tmp_repo / "setup.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.README_MD", tmp_repo / "README.md")

        msgs = replace_tokens(sample_config)

        assert isinstance(msgs, list)
        assert all(isinstance(m, str) for m in msgs)
        assert any(".sops.yaml" in m for m in msgs)
        assert any("setup.sh" in m for m in msgs)
        assert any("bootstrap.sh" in m for m in msgs)
        assert any("README.md" in m for m in msgs)

    def test_idempotent(self, tmp_repo, sample_config, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.tokens.SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr("setup_tui.lib.tokens.SETUP_SH", tmp_repo / "setup.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr("setup_tui.lib.tokens.README_MD", tmp_repo / "README.md")

        replace_tokens(sample_config)
        content_first = (tmp_repo / ".sops.yaml").read_text()

        replace_tokens(sample_config)
        content_second = (tmp_repo / ".sops.yaml").read_text()

        assert content_first == content_second


# ===========================================================================
# Encryption (no `ui` param, returns tuple)
# ===========================================================================

class TestEncryptSecretFiles:
    def test_returns_count_and_messages(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.encryption.REPO_ROOT", tmp_repo)

        count, msgs = encrypt_secret_files(mock_runner)

        assert count > 0
        assert isinstance(msgs, list)
        assert mock_runner.sops_encrypt_in_place.call_count == count

    def test_skips_already_encrypted(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.encryption.REPO_ROOT", tmp_repo)

        sops_file = tmp_repo / "shared" / "secrets" / "vars.sops.yml"
        sops_file.write_text('sops:\n  age: []\ndata: "ENC[...]"\n')

        count, msgs = encrypt_secret_files(mock_runner)

        encrypted_files = [
            c.args[0] for c in mock_runner.sops_encrypt_in_place.call_args_list
        ]
        assert sops_file not in encrypted_files
        assert any("Already encrypted" in m for m in msgs)

    def test_skips_decrypted_directories(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.encryption.REPO_ROOT", tmp_repo)

        decrypted_dir = tmp_repo / "shared" / "secrets" / ".decrypted"
        decrypted_dir.mkdir()
        (decrypted_dir / "vars.sops.yml").write_text("git_user_email: test@test.com\n")

        count, msgs = encrypt_secret_files(mock_runner)

        encrypted_files = [
            str(c.args[0]) for c in mock_runner.sops_encrypt_in_place.call_args_list
        ]
        assert not any(".decrypted" in f for f in encrypted_files)

    def test_summary_message(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.encryption.REPO_ROOT", tmp_repo)

        count, msgs = encrypt_secret_files(mock_runner)

        assert any(f"Encrypted {count} file(s)" in m for m in msgs)


class TestWriteAndEncrypt:
    def test_no_ui_param(self, tmp_path, mock_runner):
        """write_and_encrypt takes (runner, target, content) — no ui."""
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        write_and_encrypt(mock_runner, target, "key: value")

        assert mock_runner.sops_encrypt_in_place.called

    def test_creates_tmpfile_in_target_directory(self, tmp_path, mock_runner):
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        write_and_encrypt(mock_runner, target, "key: value")

        encrypt_call = mock_runner.sops_encrypt_in_place.call_args
        encrypted_path = encrypt_call.args[0]
        assert str(encrypted_path).startswith(str(target.parent))

    def test_content_written_before_encryption(self, tmp_path, mock_runner):
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        written_content = None

        def capture_encrypt(path):
            nonlocal written_content
            written_content = path.read_text()

        mock_runner.sops_encrypt_in_place = capture_encrypt

        write_and_encrypt(mock_runner, target, "---\nkey: value")

        assert written_content is not None
        assert "key: value" in written_content

    def test_cleanup_on_failure(self, tmp_path, mock_runner):
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        mock_runner.sops_encrypt_in_place = MagicMock(
            side_effect=subprocess.CalledProcessError(1, "sops")
        )

        with pytest.raises(EncryptionError):
            write_and_encrypt(mock_runner, target, "key: value")

        tmpfiles = list(target.parent.glob(".tmp.*"))
        assert len(tmpfiles) == 0

    def test_target_file_created(self, tmp_path, mock_runner):
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        write_and_encrypt(mock_runner, target, "key: value")

        assert target.exists()

    def test_creates_parent_dirs(self, tmp_path, mock_runner):
        target = tmp_path / "deep" / "nested" / "secrets" / "vars.sops.yml"

        write_and_encrypt(mock_runner, target, "key: value")

        assert target.exists()


# ===========================================================================
# State detection
# ===========================================================================

class TestDetectResumeState:
    def test_unpersonalized(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.state.SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr("setup_tui.lib.state.REPO_ROOT", tmp_repo)

        state = detect_resume_state(mock_runner)

        assert state.is_personalized is False
        assert not state.pending

    def test_personalized(self, tmp_repo, mock_runner, monkeypatch):
        sops = tmp_repo / ".sops.yaml"
        sops.write_text("creation_rules:\n  - age: 'age1abc123'\n")
        monkeypatch.setattr("setup_tui.lib.state.SOPS_YAML", sops)
        monkeypatch.setattr("setup_tui.lib.state.REPO_ROOT", tmp_repo)

        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )
        mock_runner.sops_decrypt = MagicMock(return_value="git_user_email: PLACEHOLDER")

        state = detect_resume_state(mock_runner)

        assert state.is_personalized is True
        assert state.has_placeholder_secrets is True

    def test_pending_steps_populated(self, tmp_repo, mock_runner, monkeypatch):
        sops = tmp_repo / ".sops.yaml"
        sops.write_text("age: 'age1real'")
        monkeypatch.setattr("setup_tui.lib.state.SOPS_YAML", sops)
        monkeypatch.setattr("setup_tui.lib.state.REPO_ROOT", tmp_repo)

        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )
        mock_runner.sops_decrypt = MagicMock(return_value="")

        state = detect_resume_state(mock_runner)
        assert "set up GitHub remote" in state.pending
        assert "install pre-commit hooks" in state.pending

    def test_precommit_detected(self, tmp_repo, mock_runner, monkeypatch):
        sops = tmp_repo / ".sops.yaml"
        sops.write_text("age: 'age1real'")
        monkeypatch.setattr("setup_tui.lib.state.SOPS_YAML", sops)
        monkeypatch.setattr("setup_tui.lib.state.REPO_ROOT", tmp_repo)

        hook = tmp_repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/bash\n")

        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )
        mock_runner.sops_decrypt = MagicMock(return_value="")

        state = detect_resume_state(mock_runner)
        assert state.has_precommit is True
        assert "install pre-commit hooks" not in state.pending

    def test_no_placeholder_when_secrets_have_values(
        self, tmp_repo, mock_runner, monkeypatch
    ):
        sops = tmp_repo / ".sops.yaml"
        sops.write_text("age: 'age1real'")
        monkeypatch.setattr("setup_tui.lib.state.SOPS_YAML", sops)
        monkeypatch.setattr("setup_tui.lib.state.REPO_ROOT", tmp_repo)

        vars_file = tmp_repo / "shared" / "secrets" / "vars.sops.yml"
        vars_file.write_text('sops:\n  age: []\n')
        mock_runner.sops_decrypt = MagicMock(
            return_value='git_user_email: "real@email.com"'
        )
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )

        state = detect_resume_state(mock_runner)
        assert state.has_placeholder_secrets is False


class TestExtractResumeConfig:
    def test_extracts_from_setup_sh(self, tmp_repo, mock_runner, monkeypatch):
        setup_sh = tmp_repo / "setup.sh"
        setup_sh.write_text(
            '#!/usr/bin/env bash\n'
            'git clone "https://github.com/myuser/my-ws.git" ~/.workstation\n'
        )
        monkeypatch.setattr("setup_tui.lib.state.SETUP_SH", setup_sh)
        monkeypatch.setattr("setup_tui.lib.state.AGE_KEY_PATH", tmp_repo / "nokey")

        mock_runner.age_public_key_from_file = MagicMock(return_value="")
        mock_runner.run = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )

        config = extract_resume_config(mock_runner)

        assert config.github_username == "myuser"
        assert config.repo_name == "my-ws"
        assert config.github_repo_url == "https://github.com/myuser/my-ws.git"

    def test_falls_back_to_git_remote(self, tmp_repo, mock_runner, monkeypatch):
        setup_sh = tmp_repo / "setup.sh"
        setup_sh.write_text("#!/usr/bin/env bash\necho hello\n")  # no URL
        monkeypatch.setattr("setup_tui.lib.state.SETUP_SH", setup_sh)
        monkeypatch.setattr("setup_tui.lib.state.AGE_KEY_PATH", tmp_repo / "nokey")

        mock_runner.age_public_key_from_file = MagicMock(return_value="")
        mock_runner.run = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="https://github.com/remoteuser/remote-repo.git",
                stderr=""
            )
        )

        config = extract_resume_config(mock_runner)

        assert config.github_username == "remoteuser"
        assert config.repo_name == "remote-repo"

    def test_raises_if_no_url_found(self, tmp_repo, mock_runner, monkeypatch):
        setup_sh = tmp_repo / "setup.sh"
        setup_sh.write_text("#!/usr/bin/env bash\necho hello\n")
        monkeypatch.setattr("setup_tui.lib.state.SETUP_SH", setup_sh)
        monkeypatch.setattr("setup_tui.lib.state.AGE_KEY_PATH", tmp_repo / "nokey")

        mock_runner.age_public_key_from_file = MagicMock(return_value="")
        mock_runner.run = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )

        with pytest.raises(RuntimeError, match="Could not determine repo info"):
            extract_resume_config(mock_runner)

    def test_loads_existing_age_key(self, tmp_repo, mock_runner, monkeypatch):
        key_file = tmp_repo / "keys.txt"
        key_file.write_text("AGE-SECRET-KEY-1ABC\n")
        monkeypatch.setattr("setup_tui.lib.state.AGE_KEY_PATH", key_file)

        setup_sh = tmp_repo / "setup.sh"
        setup_sh.write_text(
            'git clone "https://github.com/u/r.git" ~/.workstation\n'
        )
        monkeypatch.setattr("setup_tui.lib.state.SETUP_SH", setup_sh)

        mock_runner.age_public_key_from_file = MagicMock(return_value="age1pubkey")

        config = extract_resume_config(mock_runner)

        assert config.age_public_key == "age1pubkey"
        mock_runner.age_public_key_from_file.assert_called_once_with(key_file)


# ===========================================================================
# Git operations (no `ui` param, no confirm prompt)
# ===========================================================================

class TestDetachFromTemplate:
    def test_no_origin_returns_none(self, mock_runner, sample_config):
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )

        result = detach_from_template(mock_runner, sample_config)

        assert result is None

    def test_matching_origin(self, mock_runner, sample_config):
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="https://github.com/testuser/my-workstation.git",
                stderr="",
            )
        )

        result = detach_from_template(mock_runner, sample_config)

        assert "already points to" in result

    def test_mismatched_origin(self, mock_runner, sample_config):
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="https://github.com/template-owner/template-repo.git",
                stderr="",
            )
        )

        result = detach_from_template(mock_runner, sample_config)

        assert "does not match" in result
        assert "template-owner" in result


class TestRemoveOrigin:
    def test_calls_git_remote_remove(self, mock_runner):
        remove_origin(mock_runner)
        mock_runner.git.assert_called_once_with("remote", "remove", "origin")


class TestCreateGithubRepo:
    def test_creates_new_repo(self, mock_runner, sample_config, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", Path("/tmp/test"))

        # gh auth ok, repo doesn't exist, creation succeeds.
        def gh_side_effect(*args, **kwargs):
            if args[:2] == ("auth", "status"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            if args[:2] == ("repo", "view"):
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        mock_runner.gh = MagicMock(side_effect=gh_side_effect)

        msgs = create_github_repo(mock_runner, sample_config)

        assert any("Creating" in m for m in msgs)
        assert any("Remote set to" in m for m in msgs)

    def test_existing_repo_adds_remote(self, mock_runner, sample_config, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", Path("/tmp/test"))

        def gh_side_effect(*args, **kwargs):
            if args[:2] == ("auth", "status"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            if args[:2] == ("repo", "view"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="exists", stderr=""
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        mock_runner.gh = MagicMock(side_effect=gh_side_effect)

        msgs = create_github_repo(mock_runner, sample_config)

        assert any("already exists" in m for m in msgs)
        mock_runner.git.assert_called_once_with(
            "remote", "add", "origin", sample_config.github_repo_url
        )

    def test_public_repo_flag(self, mock_runner, sample_config, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", Path("/tmp/test"))

        def gh_side_effect(*args, **kwargs):
            if args[:2] == ("auth", "status"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            if args[:2] == ("repo", "view"):
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        mock_runner.gh = MagicMock(side_effect=gh_side_effect)

        create_github_repo(mock_runner, sample_config, public=True)

        create_call = [
            c for c in mock_runner.gh.call_args_list
            if len(c.args) >= 2 and c.args[:2] == ("repo", "create")
        ]
        assert len(create_call) == 1
        assert "--public" in create_call[0].args


class TestCommitAndPush:
    def test_returns_messages(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", tmp_repo)

        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
        )

        msgs = commit_and_push(mock_runner)

        assert isinstance(msgs, list)
        assert len(msgs) > 0

    def test_stages_personalized_files(self, mock_runner, tmp_repo, monkeypatch):
        """Commit stages all personalized config files."""
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", tmp_repo)

        def git_side_effect(*args, **kwargs):
            if args == ("diff", "--cached", "--quiet"):
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                )
            if args[:2] == ("remote", "get-url"):
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        mock_runner.git = MagicMock(side_effect=git_side_effect)

        commit_and_push(mock_runner)

        mock_runner.git.assert_any_call(
            "add", ".sops.yaml", "setup.sh", "bootstrap.sh", "README.md"
        )

    def test_nothing_to_commit(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", tmp_repo)

        def git_side_effect(*args, **kwargs):
            if args == ("diff", "--cached", "--quiet"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            if args[:2] == ("remote", "get-url"):
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        mock_runner.git = MagicMock(side_effect=git_side_effect)

        msgs = commit_and_push(mock_runner)

        assert any("Nothing to commit" in m for m in msgs)
        commit_calls = [
            c for c in mock_runner.git.call_args_list
            if len(c.args) >= 1 and c.args[0] == "commit"
        ]
        assert len(commit_calls) == 0

    def test_no_origin_skips_push(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", tmp_repo)

        def git_side_effect(*args, **kwargs):
            if args == ("diff", "--cached", "--quiet"):
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                )
            if args[:2] == ("remote", "get-url"):
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        mock_runner.git = MagicMock(side_effect=git_side_effect)

        msgs = commit_and_push(mock_runner)

        assert any("Committed locally" in m for m in msgs)
        push_calls = [
            c for c in mock_runner.git.call_args_list
            if len(c.args) >= 1 and c.args[0] == "push"
        ]
        assert len(push_calls) == 0

    def test_refuses_push_on_unrelated_history(
        self, mock_runner, tmp_repo, monkeypatch
    ):
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", tmp_repo)

        def git_side_effect(*args, **kwargs):
            if args == ("diff", "--cached", "--quiet"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            if args[:2] == ("remote", "get-url"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="https://github.com/u/r.git", stderr=""
                )
            if args[:3] == ("ls-remote", "--refs", "origin"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="abc123\tHEAD", stderr=""
                )
            if args[0] == "merge-base":
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        mock_runner.git = MagicMock(side_effect=git_side_effect)

        msgs = commit_and_push(mock_runner)

        assert any("don't share history" in m or "Refusing" in m for m in msgs)
        push_calls = [
            c for c in mock_runner.git.call_args_list
            if len(c.args) >= 1 and c.args[0] == "push"
        ]
        assert len(push_calls) == 0

    def test_successful_push(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", tmp_repo)

        def git_side_effect(*args, **kwargs):
            if args == ("diff", "--cached", "--quiet"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            if args[:2] == ("remote", "get-url"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="https://github.com/u/r.git", stderr=""
                )
            if args[:3] == ("ls-remote", "--refs", "origin"):
                # Empty remote (new repo, no commits).
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        mock_runner.git = MagicMock(side_effect=git_side_effect)

        msgs = commit_and_push(mock_runner)

        assert any("Pushed" in m for m in msgs)

    def test_push_failure_workflow_hint(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", tmp_repo)

        def git_side_effect(*args, **kwargs):
            if args == ("diff", "--cached", "--quiet"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            if args[:2] == ("remote", "get-url"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="https://github.com/u/r.git", stderr=""
                )
            if args[:3] == ("ls-remote", "--refs", "origin"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            if args[0] == "push":
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="",
                    stderr="refusing to allow a GitHub workflow to push"
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        mock_runner.git = MagicMock(side_effect=git_side_effect)

        msgs = commit_and_push(mock_runner)

        assert any("workflow" in m for m in msgs)

    def test_initializes_git_if_no_git_dir(self, mock_runner, tmp_path, monkeypatch):
        """If .git doesn't exist, should git init + branch -M main."""
        monkeypatch.setattr("setup_tui.lib.git_ops.REPO_ROOT", tmp_path)

        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
        )

        commit_and_push(mock_runner)

        mock_runner.git.assert_any_call("init")
        mock_runner.git.assert_any_call("branch", "-M", "main")


# ===========================================================================
# Age key
# ===========================================================================

class TestGenerateOrLoadAgeKey:
    def test_generates_new_key(self, mock_runner, tmp_path, monkeypatch):
        key_path = tmp_path / "keys.txt"
        monkeypatch.setattr("setup_tui.lib.age.AGE_KEY_PATH", key_path)

        status, pubkey = generate_or_load_age_key(mock_runner)

        assert "generated" in status.lower()
        assert pubkey == "age1abc"
        assert key_path.exists()
        assert key_path.read_text() == "private-key\n"
        mock_runner.age_keygen.assert_called_once()

    def test_loads_existing_key(self, mock_runner, tmp_path, monkeypatch):
        key_path = tmp_path / "keys.txt"
        key_path.write_text("AGE-SECRET-KEY-1ABC\n")
        monkeypatch.setattr("setup_tui.lib.age.AGE_KEY_PATH", key_path)

        status, pubkey = generate_or_load_age_key(mock_runner)

        assert "exists" in status.lower()
        assert pubkey == "age1abc"
        mock_runner.age_keygen.assert_not_called()

    def test_raises_on_missing_public_key(self, mock_runner, tmp_path, monkeypatch):
        key_file = tmp_path / "keys.txt"
        key_file.write_text("# existing but bad\n")
        monkeypatch.setattr("setup_tui.lib.age.AGE_KEY_PATH", key_file)

        mock_runner.age_public_key_from_file = MagicMock(return_value="")

        with pytest.raises(AgeKeyError):
            generate_or_load_age_key(mock_runner)

    def test_raises_on_empty_keygen_output(self, mock_runner, tmp_path, monkeypatch):
        key_path = tmp_path / "keys.txt"
        monkeypatch.setattr("setup_tui.lib.age.AGE_KEY_PATH", key_path)

        mock_runner.age_keygen = MagicMock(return_value=("private-key", ""))

        with pytest.raises(AgeKeyError, match="did not produce"):
            generate_or_load_age_key(mock_runner)

    def test_key_file_permissions(self, mock_runner, tmp_path, monkeypatch):
        key_path = tmp_path / "subdir" / "keys.txt"
        monkeypatch.setattr("setup_tui.lib.age.AGE_KEY_PATH", key_path)

        generate_or_load_age_key(mock_runner)

        assert key_path.stat().st_mode & 0o777 == 0o600
        assert key_path.parent.stat().st_mode & 0o777 == 0o700


# ===========================================================================
# Secrets load/save helpers
# ===========================================================================

class TestLoadExistingAnsibleVars:
    def test_loads_decrypted_yaml(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(
            return_value='---\ngit_user_email: "test@example.com"\ngit_user_name: "Test"\n'
        )

        result = load_existing_ansible_vars(mock_runner)

        assert result["git_user_email"] == "test@example.com"
        assert result["git_user_name"] == "Test"

    def test_skips_placeholder_values(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(
            return_value='---\ngit_user_email: PLACEHOLDER\n'
        )

        result = load_existing_ansible_vars(mock_runner)

        assert "git_user_email" not in result

    def test_missing_file_returns_empty(self, tmp_path, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_path)

        result = load_existing_ansible_vars(mock_runner)

        assert result == {}

    def test_skips_comments_and_separators(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(
            return_value='---\n# comment\ngit_user_email: "a@b.com"\n'
        )

        result = load_existing_ansible_vars(mock_runner)

        assert "git_user_email" in result
        assert len(result) == 1  # no comment key


class TestLoadExistingShellExports:
    def test_loads_export_statements(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(
            return_value='# Shell secrets\nexport ANTHROPIC_API_KEY="sk-ant-123"\nexport OTHER="val"\n'
        )

        result = load_existing_shell_exports(mock_runner)

        assert result["ANTHROPIC_API_KEY"] == "sk-ant-123"
        assert result["OTHER"] == "val"

    def test_skips_non_export_lines(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(
            return_value='# comment\nexport KEY="val"\nsome other line\n'
        )

        result = load_existing_shell_exports(mock_runner)

        assert len(result) == 1
        assert result["KEY"] == "val"

    def test_missing_file_returns_empty(self, tmp_path, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_path)

        result = load_existing_shell_exports(mock_runner)

        assert result == {}


class TestSaveAnsibleVars:
    def test_writes_yaml_and_encrypts(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_repo)

        written_content = None

        def capture_encrypt(path):
            nonlocal written_content
            written_content = path.read_text()

        mock_runner.sops_encrypt_in_place = capture_encrypt

        save_ansible_vars(mock_runner, {
            "git_user_email": "a@b.com",
            "git_user_name": "Test",
        })

        assert written_content is not None
        assert 'git_user_email: "a@b.com"' in written_content
        assert 'git_user_name: "Test"' in written_content
        assert written_content.startswith("---\n")


class TestSaveShellExports:
    def test_writes_exports_and_encrypts(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_repo)

        written_content = None

        def capture_encrypt(path):
            nonlocal written_content
            written_content = path.read_text()

        mock_runner.sops_encrypt_in_place = capture_encrypt

        save_shell_exports(mock_runner, {
            "ANTHROPIC_API_KEY": "sk-ant-123",
            "OTHER_KEY": "val",
        })

        assert written_content is not None
        assert 'export ANTHROPIC_API_KEY="sk-ant-123"' in written_content
        assert 'export OTHER_KEY="val"' in written_content
        assert "Shell secrets" in written_content

    def test_empty_dict_no_write(self, tmp_repo, mock_runner, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.secrets.REPO_ROOT", tmp_repo)

        save_shell_exports(mock_runner, {})

        mock_runner.sops_encrypt_in_place.assert_not_called()


# ===========================================================================
# Prereqs
# ===========================================================================

class TestInstallPrecommit:
    def test_already_installed(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.prereqs.REPO_ROOT", tmp_repo)

        hook = tmp_repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/bash\n")

        msgs = install_precommit(mock_runner)

        assert any("already installed" in m for m in msgs)

    def test_installs_via_uv(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.prereqs.REPO_ROOT", tmp_repo)

        hook = tmp_repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/bash\n")

        call_count = [0]

        def command_exists(cmd):
            if cmd == "pre-commit":
                call_count[0] += 1
                return call_count[0] > 1  # False first, True after "install"
            return cmd == "uv"

        mock_runner.command_exists = MagicMock(side_effect=command_exists)

        msgs = install_precommit(mock_runner)

        assert any("Installing pre-commit" in m for m in msgs)
        mock_runner.run.assert_any_call(["uv", "tool", "install", "pre-commit"])

    def test_installs_via_pip3_fallback(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.prereqs.REPO_ROOT", tmp_repo)

        hook = tmp_repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/bash\n")

        call_count = [0]

        def command_exists(cmd):
            if cmd == "pre-commit":
                call_count[0] += 1
                return call_count[0] > 1
            if cmd == "uv":
                return False
            return cmd == "pip3"

        mock_runner.command_exists = MagicMock(side_effect=command_exists)

        install_precommit(mock_runner)

        mock_runner.run.assert_any_call(
            ["pip3", "install", "--user", "pre-commit"]
        )

    def test_raises_if_no_installer(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.prereqs.REPO_ROOT", tmp_repo)

        def command_exists(cmd):
            return False  # Nothing is available.

        mock_runner.command_exists = MagicMock(side_effect=command_exists)

        with pytest.raises(RuntimeError, match="Neither uv nor pip3"):
            install_precommit(mock_runner)

    def test_raises_if_install_fails(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.prereqs.REPO_ROOT", tmp_repo)

        def command_exists(cmd):
            if cmd == "pre-commit":
                return False  # Never succeeds.
            return cmd == "uv"

        mock_runner.command_exists = MagicMock(side_effect=command_exists)

        with pytest.raises(RuntimeError, match="installation failed"):
            install_precommit(mock_runner)

    def test_raises_if_hook_not_created(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.prereqs.REPO_ROOT", tmp_repo)

        # pre-commit exists, but hook file doesn't get created.
        mock_runner.command_exists = MagicMock(return_value=True)
        # Don't create the hook file — .git/hooks/pre-commit won't exist.

        with pytest.raises(RuntimeError, match="not installed into .git/hooks"):
            install_precommit(mock_runner)

    def test_installs_hooks_in_git_repo(self, mock_runner, tmp_repo, monkeypatch):
        monkeypatch.setattr("setup_tui.lib.prereqs.REPO_ROOT", tmp_repo)

        hook = tmp_repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/bash\n")

        install_precommit(mock_runner)

        mock_runner.run.assert_any_call(
            ["pre-commit", "install"], cwd=tmp_repo
        )


# ===========================================================================
# Logging
# ===========================================================================

class TestSetupLogging:
    def test_creates_log_directory(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "log"
        log_file = log_dir / "setup.log"
        monkeypatch.setattr("setup_tui.lib.setup_logging.LOG_DIR", log_dir)
        monkeypatch.setattr("setup_tui.lib.setup_logging.LOG_FILE", log_file)

        # Clear any existing handlers from prior tests.
        logger = logging.getLogger("setup")
        logger.handlers.clear()

        setup_logging(debug=False)

        assert log_dir.exists()

    def test_writes_to_log_file(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "log"
        log_file = log_dir / "setup.log"
        monkeypatch.setattr("setup_tui.lib.setup_logging.LOG_DIR", log_dir)
        monkeypatch.setattr("setup_tui.lib.setup_logging.LOG_FILE", log_file)

        logger = logging.getLogger("setup")
        logger.handlers.clear()

        setup_logging(debug=False)

        assert log_file.exists()
        content = log_file.read_text()
        assert "setup.py" in content
        assert "platform:" in content

    def test_debug_adds_console_handler(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "log"
        log_file = log_dir / "setup.log"
        monkeypatch.setattr("setup_tui.lib.setup_logging.LOG_DIR", log_dir)
        monkeypatch.setattr("setup_tui.lib.setup_logging.LOG_FILE", log_file)

        logger = logging.getLogger("setup")
        logger.handlers.clear()

        setup_logging(debug=True)

        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler in handler_types
        assert logging.FileHandler in handler_types

    def test_no_console_handler_without_debug(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "log"
        log_file = log_dir / "setup.log"
        monkeypatch.setattr("setup_tui.lib.setup_logging.LOG_DIR", log_dir)
        monkeypatch.setattr("setup_tui.lib.setup_logging.LOG_FILE", log_file)

        logger = logging.getLogger("setup")
        logger.handlers.clear()

        setup_logging(debug=False)

        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler not in handler_types
        assert logging.FileHandler in handler_types

    def test_log_constants(self):
        assert LOG_DIR == Path.home() / ".local" / "log"
        assert LOG_FILE == Path.home() / ".local" / "log" / "setup.log"


# ===========================================================================
# ToolRunner
# ===========================================================================

class TestToolRunner:
    def test_init_debug_flag(self):
        runner = ToolRunner(debug=True)
        assert runner.debug is True

        runner2 = ToolRunner(debug=False)
        assert runner2.debug is False

    def test_command_exists_true(self):
        runner = ToolRunner()
        assert runner.command_exists("python3") is True

    def test_command_exists_false(self):
        runner = ToolRunner()
        assert runner.command_exists("nonexistent_command_xyz_123") is False

    def test_repo_root_is_valid(self):
        """REPO_ROOT should point to the actual repo root."""
        assert REPO_ROOT.is_dir()
        assert (REPO_ROOT / "Makefile").exists()
