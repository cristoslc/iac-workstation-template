"""Tests for Phase 6 encryption and the write_and_encrypt helper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import importlib

first_run = importlib.import_module("first-run")


class TestEncryptSecretFiles:
    """Tests for encrypt_secret_files()."""

    def test_finds_sops_files_in_secrets_dirs(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """Should find and encrypt .sops files inside secrets/ directories."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        # The tmp_repo fixture creates files in shared/secrets/ and platform/secrets/.
        count = first_run.encrypt_secret_files(mock_runner, mock_ui)

        # Should have encrypted shared + macos + linux vars + shell secrets.
        assert count > 0
        assert mock_runner.sops_encrypt_in_place.call_count == count

    def test_skips_already_encrypted_files(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """Files with sops metadata should be skipped."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        # Add sops metadata to one file.
        sops_file = tmp_repo / "shared" / "secrets" / "vars.sops.yml"
        sops_file.write_text('sops:\n  age: []\ndata: "ENC[...]"\n')

        count = first_run.encrypt_secret_files(mock_runner, mock_ui)

        # The shared vars file should be skipped.
        encrypted_files = [
            c.args[0] for c in mock_runner.sops_encrypt_in_place.call_args_list
        ]
        assert sops_file not in encrypted_files

    def test_skips_decrypted_directories(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """Files in .decrypted/ directories should be skipped."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        # Create a file in .decrypted/.
        decrypted_dir = tmp_repo / "shared" / "secrets" / ".decrypted"
        decrypted_dir.mkdir()
        (decrypted_dir / "vars.sops.yml").write_text("git_user_email: test@test.com\n")

        count = first_run.encrypt_secret_files(mock_runner, mock_ui)

        encrypted_files = [
            str(c.args[0]) for c in mock_runner.sops_encrypt_in_place.call_args_list
        ]
        assert not any(".decrypted" in f for f in encrypted_files)

    def test_ignores_sops_config_file(
        self, tmp_repo, mock_runner, mock_ui, monkeypatch
    ):
        """The .sops.yaml config at repo root should NOT be encrypted."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        count = first_run.encrypt_secret_files(mock_runner, mock_ui)

        encrypted_files = [
            str(c.args[0]) for c in mock_runner.sops_encrypt_in_place.call_args_list
        ]
        assert not any(f.endswith(".sops.yaml") and "/secrets/" not in f for f in encrypted_files)


class TestWriteAndEncrypt:
    """Tests for write_and_encrypt() helper."""

    def test_creates_tmpfile_in_target_directory(
        self, tmp_path, mock_runner, mock_ui
    ):
        """Temp file must be in the target's directory for SOPS path_regex match."""
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        first_run.write_and_encrypt(
            mock_runner, target, "key: value", mock_ui
        )

        # The sops_encrypt_in_place call should get a path in the target dir.
        encrypt_call = mock_runner.sops_encrypt_in_place.call_args
        encrypted_path = encrypt_call.args[0]
        assert str(encrypted_path).startswith(str(target.parent))

    def test_content_written_before_encryption(
        self, tmp_path, mock_runner, mock_ui
    ):
        """The plaintext content should be written before sops encrypts."""
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        written_content = None

        def capture_encrypt(path):
            nonlocal written_content
            written_content = path.read_text()

        mock_runner.sops_encrypt_in_place = capture_encrypt

        first_run.write_and_encrypt(
            mock_runner, target, "---\nkey: value", mock_ui
        )

        assert written_content is not None
        assert "key: value" in written_content

    def test_cleanup_on_failure(self, tmp_path, mock_runner, mock_ui):
        """If encryption fails, temp file should be removed."""
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        mock_runner.sops_encrypt_in_place = MagicMock(
            side_effect=subprocess.CalledProcessError(1, "sops")
        )

        with pytest.raises(first_run.EncryptionError):
            first_run.write_and_encrypt(
                mock_runner, target, "key: value", mock_ui
            )

        # No leftover temp files.
        tmpfiles = list(target.parent.glob(".tmp.*"))
        assert len(tmpfiles) == 0

    def test_target_file_created(self, tmp_path, mock_runner, mock_ui):
        """After successful encryption, target file should exist."""
        target = tmp_path / "secrets" / "vars.sops.yml"
        target.parent.mkdir(parents=True)

        first_run.write_and_encrypt(
            mock_runner, target, "key: value", mock_ui
        )

        assert target.exists()
