"""Tests for Phase 5: template token replacement."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import importlib

first_run = importlib.import_module("first-run")


class TestReplaceTokens:
    """Tests for replace_tokens()."""

    def test_substitutes_age_key_in_sops_yaml(
        self, tmp_repo, sample_config, mock_ui, monkeypatch
    ):
        """${AGE_PUBLIC_KEY} in .sops.yaml should be replaced."""
        monkeypatch.setattr(first_run, "SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr(first_run, "BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr(first_run, "README_MD", tmp_repo / "README.md")

        first_run.replace_tokens(sample_config, mock_ui)

        content = (tmp_repo / ".sops.yaml").read_text()
        assert "${AGE_PUBLIC_KEY}" not in content
        assert sample_config.age_public_key in content

    def test_substitutes_repo_url_in_bootstrap(
        self, tmp_repo, sample_config, mock_ui, monkeypatch
    ):
        """${GITHUB_REPO_URL} in bootstrap.sh should be replaced."""
        monkeypatch.setattr(first_run, "SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr(first_run, "BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr(first_run, "README_MD", tmp_repo / "README.md")

        first_run.replace_tokens(sample_config, mock_ui)

        content = (tmp_repo / "bootstrap.sh").read_text()
        assert "${GITHUB_REPO_URL}" not in content
        assert sample_config.github_repo_url in content

    def test_preserves_bash_variables(
        self, tmp_repo, sample_config, mock_ui, monkeypatch
    ):
        """${BASH_SOURCE[0]} and other bash vars must NOT be replaced."""
        monkeypatch.setattr(first_run, "SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr(first_run, "BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr(first_run, "README_MD", tmp_repo / "README.md")

        first_run.replace_tokens(sample_config, mock_ui)

        content = (tmp_repo / "bootstrap.sh").read_text()
        assert "${BASH_SOURCE[0]}" in content

    def test_substitutes_all_readme_tokens(
        self, tmp_repo, sample_config, mock_ui, monkeypatch
    ):
        """All three tokens in README.md should be replaced."""
        monkeypatch.setattr(first_run, "SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr(first_run, "BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr(first_run, "README_MD", tmp_repo / "README.md")

        first_run.replace_tokens(sample_config, mock_ui)

        content = (tmp_repo / "README.md").read_text()
        assert "${GITHUB_REPO_URL}" not in content
        assert "${GITHUB_USERNAME}" not in content
        assert "${REPO_NAME}" not in content
        assert sample_config.github_repo_url in content
        assert sample_config.github_username in content
        assert sample_config.repo_name in content

    def test_bootstrap_executable_after_replacement(
        self, tmp_repo, sample_config, mock_ui, monkeypatch
    ):
        """bootstrap.sh should be executable (chmod 755) after replacement."""
        monkeypatch.setattr(first_run, "SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr(first_run, "BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr(first_run, "README_MD", tmp_repo / "README.md")

        first_run.replace_tokens(sample_config, mock_ui)

        mode = (tmp_repo / "bootstrap.sh").stat().st_mode
        assert mode & 0o755 == 0o755

    def test_idempotent_replacement(
        self, tmp_repo, sample_config, mock_ui, monkeypatch
    ):
        """Running replace_tokens twice should produce the same result."""
        monkeypatch.setattr(first_run, "SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr(first_run, "BOOTSTRAP_SH", tmp_repo / "bootstrap.sh")
        monkeypatch.setattr(first_run, "README_MD", tmp_repo / "README.md")

        first_run.replace_tokens(sample_config, mock_ui)
        content_after_first = (tmp_repo / ".sops.yaml").read_text()

        first_run.replace_tokens(sample_config, mock_ui)
        content_after_second = (tmp_repo / ".sops.yaml").read_text()

        assert content_after_first == content_after_second
