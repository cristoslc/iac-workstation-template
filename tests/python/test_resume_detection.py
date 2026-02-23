"""Tests for Phase 2: resume detection and re-run handling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import importlib

first_run = importlib.import_module("first-run")


class TestDetectResumeState:
    """Tests for detect_resume_state()."""

    def test_unpersonalized_sops_yaml(self, tmp_repo, mock_runner, monkeypatch):
        """When .sops.yaml still has the template token, is_personalized=False."""
        monkeypatch.setattr(first_run, "SOPS_YAML", tmp_repo / ".sops.yaml")
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)
        state = first_run.detect_resume_state(mock_runner)
        assert state.is_personalized is False
        # No further checks should happen.
        assert not state.pending

    def test_personalized_sops_yaml(self, tmp_repo, mock_runner, monkeypatch):
        """When .sops.yaml has a real key, is_personalized=True."""
        sops = tmp_repo / ".sops.yaml"
        sops.write_text(
            "creation_rules:\n"
            "  - path_regex: '.*/secrets/.*'\n"
            "    age: 'age1abc123'\n"
        )
        monkeypatch.setattr(first_run, "SOPS_YAML", sops)
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        # Mock git commands to indicate nothing is set up.
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )
        mock_runner.sops_decrypt = MagicMock(return_value="git_user_email: PLACEHOLDER")

        state = first_run.detect_resume_state(mock_runner)
        assert state.is_personalized is True
        assert state.has_placeholder_secrets is True

    def test_pending_steps_populated(self, tmp_repo, mock_runner, monkeypatch):
        """Pending steps should list what's incomplete."""
        sops = tmp_repo / ".sops.yaml"
        sops.write_text("age: 'age1real'")
        monkeypatch.setattr(first_run, "SOPS_YAML", sops)
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        # No origin, no pre-commit hook.
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )
        mock_runner.sops_decrypt = MagicMock(return_value="")

        state = first_run.detect_resume_state(mock_runner)
        assert "set up GitHub remote" in state.pending
        assert "install pre-commit hooks" in state.pending

    def test_precommit_detected(self, tmp_repo, mock_runner, monkeypatch):
        """Pre-commit hook file existence should be detected."""
        sops = tmp_repo / ".sops.yaml"
        sops.write_text("age: 'age1real'")
        monkeypatch.setattr(first_run, "SOPS_YAML", sops)
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)

        # Create pre-commit hook file.
        hook = tmp_repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/bash\n")

        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )
        mock_runner.sops_decrypt = MagicMock(return_value="")

        state = first_run.detect_resume_state(mock_runner)
        assert state.has_precommit is True
        assert "install pre-commit hooks" not in state.pending


class TestHandleRerun:
    """Tests for handle_rerun()."""

    def test_all_complete_no_placeholders_exit(
        self, mock_runner, mock_ui
    ):
        """When everything is done, choosing not to re-run returns 'exit'."""
        state = first_run.ResumeState(
            is_personalized=True,
            has_origin=True,
            has_commit=True,
            is_pushed=True,
            has_precommit=True,
            has_placeholder_secrets=False,
        )
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="https://github.com/u/r.git", stderr=""
            )
        )
        mock_ui.confirm = MagicMock(return_value=False)

        result = first_run.handle_rerun(mock_runner, mock_ui, state)
        assert result == "exit"

    def test_placeholder_edit_secrets(self, mock_runner, mock_ui):
        """When placeholders remain, choosing edit returns 'edit-secrets'."""
        state = first_run.ResumeState(
            is_personalized=True,
            has_placeholder_secrets=True,
        )
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="https://github.com/u/r.git", stderr=""
            )
        )
        mock_ui.choose = MagicMock(return_value="Edit secrets now")

        result = first_run.handle_rerun(mock_runner, mock_ui, state)
        assert result == "edit-secrets"

    def test_pending_resume(self, mock_runner, mock_ui):
        """When steps are pending, choosing resume returns 'resume'."""
        state = first_run.ResumeState(
            is_personalized=True,
            pending=["push to remote"],
        )
        mock_ui.choose = MagicMock(return_value="Resume from where it left off")

        result = first_run.handle_rerun(mock_runner, mock_ui, state)
        assert result == "resume"
