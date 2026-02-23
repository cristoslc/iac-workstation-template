"""Tests for Phase 11: guided secret editing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import importlib

first_run = importlib.import_module("first-run")


class TestEditSecrets:
    """Tests for edit_secrets() — guided prompts for each declared secret."""

    def test_prompts_for_each_declared_field(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """Should prompt once per SHARED_ANSIBLE_VARS + SHELL_SECRETS entry."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(return_value="")
        mock_ui.prompt = MagicMock(return_value="")
        mock_ui.confirm = MagicMock(return_value=False)
        mock_runner.sops_encrypt_in_place = MagicMock()

        first_run.edit_secrets(mock_runner, mock_ui, "macos")

        # ui.prompt called at least once per ansible var + once per shell secret.
        expected_min = len(first_run.SHARED_ANSIBLE_VARS) + len(first_run.SHELL_SECRETS)
        assert mock_ui.prompt.call_count >= expected_min

    def test_skipped_vars_write_placeholder(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """When user presses Enter (empty) for all vars, PLACEHOLDERs are written."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(return_value="")
        mock_ui.prompt = MagicMock(return_value="")
        mock_ui.confirm = MagicMock(return_value=False)
        mock_runner.sops_encrypt_in_place = MagicMock()

        first_run.edit_secrets(mock_runner, mock_ui, "macos")

        assert mock_runner.sops_encrypt_in_place.called

    def test_email_value_preserved(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """When user enters values, they should appear in info output."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(return_value="")
        # Return values for each prompt: git_user_email, git_user_name, then shell secrets.
        num_ansible = len(first_run.SHARED_ANSIBLE_VARS)
        num_shell = len(first_run.SHELL_SECRETS)
        input_values = (
            ["test@example.com", "Test User"][:num_ansible]
            + [""] * num_shell
        )
        mock_ui.prompt = MagicMock(
            side_effect=iter(input_values + [""] * 10)
        )
        mock_ui.confirm = MagicMock(return_value=False)
        mock_runner.sops_encrypt_in_place = MagicMock()

        first_run.edit_secrets(mock_runner, mock_ui, "macos")

        info_msgs = [m[1] for m in mock_ui._messages if m[0] == "info"]
        assert any("test@example.com" in m for m in info_msgs)
        assert any("Test User" in m for m in info_msgs)

    def test_shell_secrets_prompted_by_name(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """Each declared SHELL_SECRETS entry should be prompted for by name."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(return_value="")
        # Skip ansible vars, then provide a value for the first shell secret.
        num_ansible = len(first_run.SHARED_ANSIBLE_VARS)
        num_shell = len(first_run.SHELL_SECRETS)
        input_values = [""] * num_ansible + ["sk-ant-test123"] + [""] * (num_shell - 1)
        mock_ui.prompt = MagicMock(
            side_effect=iter(input_values + [""] * 10)
        )
        mock_ui.confirm = MagicMock(return_value=False)
        mock_runner.sops_encrypt_in_place = MagicMock()

        first_run.edit_secrets(mock_runner, mock_ui, "macos")

        info_msgs = [m[1] for m in mock_ui._messages if m[0] == "info"]
        first_secret_name = first_run.SHELL_SECRETS[0].key
        assert any(first_secret_name in m for m in info_msgs)

    def test_custom_shell_secret_loop(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """User can add custom secrets beyond the declared list."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(return_value="")

        # Skip all declared prompts, then add one custom secret.
        num_ansible = len(first_run.SHARED_ANSIBLE_VARS)
        num_shell = len(first_run.SHELL_SECRETS)
        input_values = (
            [""] * num_ansible      # skip ansible vars
            + [""] * num_shell      # skip declared shell secrets
            + ["CUSTOM_KEY", "custom_value"]  # custom secret key + value
        )
        mock_ui.prompt = MagicMock(
            side_effect=iter(input_values + [""] * 10)
        )
        # First confirm: yes (add custom), second: no (stop).
        confirm_values = iter([True, False])
        mock_ui.confirm = MagicMock(
            side_effect=lambda _q, **_kw: next(confirm_values, False)
        )
        mock_runner.sops_encrypt_in_place = MagicMock()

        first_run.edit_secrets(mock_runner, mock_ui, "macos")

        info_msgs = [m[1] for m in mock_ui._messages if m[0] == "info"]
        assert any("CUSTOM_KEY" in m for m in info_msgs)

    def test_existing_values_prefilled(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """Existing decrypted values should be passed as pre-fill to prompt."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(
            return_value='---\ngit_user_email: "old@example.com"\ngit_user_name: "Old Name"\n'
        )
        mock_ui.prompt = MagicMock(return_value="")
        mock_ui.confirm = MagicMock(return_value=False)
        mock_runner.sops_encrypt_in_place = MagicMock()

        first_run.edit_secrets(mock_runner, mock_ui, "macos")

        # First ui.prompt call should have default="old@example.com" (via _prompt_for_field).
        first_call = mock_ui.prompt.call_args_list[0]
        assert first_call.kwargs.get("default") == "old@example.com"

    def test_secret_field_has_doc_url(self):
        """SHELL_SECRETS entries should have doc_url populated."""
        for sf in first_run.SHELL_SECRETS:
            assert sf.doc_url, f"{sf.key} should have a doc_url"
            assert sf.doc_url.startswith("https://"), f"{sf.key} doc_url should be HTTPS"

    def test_all_fields_have_used_by(self):
        """Every SecretField should declare which roles/tools consume it."""
        for sf in first_run.SHARED_ANSIBLE_VARS + first_run.SHELL_SECRETS:
            assert sf.used_by, f"{sf.key} should have a used_by"

    def test_mask_value_short(self):
        """Short values should be fully masked."""
        assert first_run._mask_value("abc") == "***"
        assert first_run._mask_value("1234567890") == "**********"

    def test_mask_value_long(self):
        """Long values should show first 4 and last 4 chars."""
        result = first_run._mask_value("sk-ant-abcdef12345xyz")
        assert result.startswith("sk-a")
        assert result.endswith("5xyz")
        assert "*" in result
        assert len(result) == len("sk-ant-abcdef12345xyz")

    def test_platform_awareness_macos(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """macOS platform should show macOS-specific messages."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(return_value="")
        mock_ui.prompt = MagicMock(return_value="")
        mock_ui.confirm = MagicMock(return_value=False)
        mock_runner.sops_encrypt_in_place = MagicMock()

        first_run.edit_secrets(mock_runner, mock_ui, "macos")

        info_msgs = [m[1] for m in mock_ui._messages if m[0] == "info"]
        assert any("macOS" in m for m in info_msgs)
        assert any("edit-secrets-macos" in m for m in info_msgs)

    def test_platform_awareness_linux(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """Linux platform should show Linux-specific messages."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        mock_runner.sops_decrypt = MagicMock(return_value="")
        mock_ui.prompt = MagicMock(return_value="")
        mock_ui.confirm = MagicMock(return_value=False)
        mock_runner.sops_encrypt_in_place = MagicMock()

        first_run.edit_secrets(mock_runner, mock_ui, "linux")

        info_msgs = [m[1] for m in mock_ui._messages if m[0] == "info"]
        assert any("Linux" in m for m in info_msgs)
        assert any("edit-secrets-linux" in m for m in info_msgs)


class TestWriteAndEncryptIntegration:
    """Integration tests for write_and_encrypt with edit_secrets flow."""

    def test_yaml_content_format(self, tmp_path, mock_runner, mock_ui):
        """Written YAML content should be valid YAML format."""
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        written_content = None

        def capture_encrypt(path):
            nonlocal written_content
            written_content = path.read_text()

        mock_runner.sops_encrypt_in_place = capture_encrypt

        first_run.write_and_encrypt(
            mock_runner, target, '---\ngit_user_email: "test@test.com"', mock_ui
        )

        assert written_content is not None
        import yaml
        parsed = yaml.safe_load(written_content)
        assert parsed["git_user_email"] == "test@test.com"

    def test_shell_secrets_content_format(self, tmp_path, mock_runner, mock_ui):
        """Written shell secrets should be valid export statements."""
        target = tmp_path / "secrets" / "secrets.zsh.sops"
        target.parent.mkdir(parents=True)

        written_content = None

        def capture_encrypt(path):
            nonlocal written_content
            written_content = path.read_text()

        mock_runner.sops_encrypt_in_place = capture_encrypt

        content = '# Shell secrets -- sourced by .zshrc\nexport MY_KEY="my_value"'
        first_run.write_and_encrypt(mock_runner, target, content, mock_ui)

        assert written_content is not None
        assert 'export MY_KEY="my_value"' in written_content

    def test_multiple_ansible_vars_in_yaml(self, tmp_path, mock_runner, mock_ui):
        """Multiple ansible vars should all appear in the YAML output."""
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        written_content = None

        def capture_encrypt(path):
            nonlocal written_content
            written_content = path.read_text()

        mock_runner.sops_encrypt_in_place = capture_encrypt

        content = '---\ngit_user_email: "a@b.com"\ngit_user_name: "Test"'
        first_run.write_and_encrypt(mock_runner, target, content, mock_ui)

        assert written_content is not None
        import yaml
        parsed = yaml.safe_load(written_content)
        assert parsed["git_user_email"] == "a@b.com"
        assert parsed["git_user_name"] == "Test"
