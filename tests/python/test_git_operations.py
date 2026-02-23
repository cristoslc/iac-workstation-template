"""Tests for Phases 8 and 10: git operations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import importlib

first_run = importlib.import_module("first-run")


class TestDetachFromTemplate:
    """Tests for Phase 8: detach_from_template()."""

    def test_no_origin_does_nothing(self, mock_runner, mock_ui, sample_config):
        """If no origin is set, function returns without action."""
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
        )

        first_run.detach_from_template(mock_runner, mock_ui, sample_config)

        # Should only call git once (to check origin).
        mock_runner.git.assert_called_once()

    def test_matching_origin_keeps_it(self, mock_runner, mock_ui, sample_config):
        """If origin matches expected slug, keep it."""
        mock_runner.git = MagicMock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="https://github.com/testuser/my-workstation.git",
                stderr="",
            )
        )

        first_run.detach_from_template(mock_runner, mock_ui, sample_config)

        # Should NOT call git remote remove.
        calls = [str(c) for c in mock_runner.git.call_args_list]
        assert not any("remove" in c for c in calls)

    def test_mismatched_origin_prompts(self, mock_runner, mock_ui, sample_config):
        """If origin doesn't match, should prompt to replace."""
        def git_side_effect(*args, **kwargs):
            if args[0] == "remote" and args[1] == "get-url":
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="https://github.com/template-owner/template-repo.git",
                    stderr=""
                )
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        mock_runner.git = MagicMock(side_effect=git_side_effect)
        mock_ui.confirm = MagicMock(return_value=True)

        first_run.detach_from_template(mock_runner, mock_ui, sample_config)

        mock_ui.confirm.assert_called_once()
        # Verify remote remove was called.
        mock_runner.git.assert_any_call("remote", "remove", "origin")


class TestCommitAndPush:
    """Tests for Phase 10: commit_and_push()."""

    def test_skip_on_decline(self, mock_runner, mock_ui, sample_config, monkeypatch):
        """If user declines, nothing should happen."""
        monkeypatch.setattr(first_run, "REPO_ROOT", Path("/tmp/test"))
        mock_ui.confirm = MagicMock(return_value=False)

        first_run.commit_and_push(mock_runner, mock_ui, sample_config)

        # git should not have been called beyond the initial setup.
        mock_runner.git.assert_not_called()

    def test_stages_specific_files(
        self, mock_runner, mock_ui, sample_config, tmp_repo, monkeypatch
    ):
        """Should stage -u and specific named files."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)
        mock_ui.confirm = MagicMock(return_value=True)

        # Has staged changes.
        def git_side_effect(*args, **kwargs):
            if args == ("diff", "--cached", "--quiet"):
                return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
            if args[:2] == ("remote", "get-url"):
                return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        mock_runner.git = MagicMock(side_effect=git_side_effect)

        first_run.commit_and_push(mock_runner, mock_ui, sample_config)

        # Verify add -u and specific files.
        mock_runner.git.assert_any_call("add", "-u")
        mock_runner.git.assert_any_call("add", ".sops.yaml", "bootstrap.sh", "README.md")

    def test_merge_base_safety_check(
        self, mock_runner, mock_ui, sample_config, tmp_repo, monkeypatch
    ):
        """Push should verify merge-base ancestry."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)
        mock_ui.confirm = MagicMock(return_value=True)

        def git_side_effect(*args, **kwargs):
            if args == ("diff", "--cached", "--quiet"):
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            if len(args) >= 2 and args[0] == "remote" and args[1] == "get-url":
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="https://github.com/testuser/my-workstation.git",
                    stderr=""
                )
            if len(args) >= 1 and args[0] == "ls-remote":
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="abc123\tHEAD",
                    stderr=""
                )
            if len(args) >= 1 and args[0] == "merge-base":
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        mock_runner.git = MagicMock(side_effect=git_side_effect)

        first_run.commit_and_push(mock_runner, mock_ui, sample_config)

        # Verify merge-base was called.
        merge_base_calls = [
            c for c in mock_runner.git.call_args_list
            if len(c.args) >= 1 and c.args[0] == "merge-base"
        ]
        assert len(merge_base_calls) > 0

    def test_refuses_push_on_unrelated_history(
        self, mock_runner, mock_ui, sample_config, tmp_repo, monkeypatch
    ):
        """Should warn and refuse push if histories don't share ancestry."""
        monkeypatch.setattr(first_run, "REPO_ROOT", tmp_repo)
        mock_ui.confirm = MagicMock(return_value=True)

        def git_side_effect(*args, **kwargs):
            check = kwargs.get("check", True)
            if args == ("diff", "--cached", "--quiet"):
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            if args[:2] == ("remote", "get-url"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="https://github.com/testuser/my-workstation.git",
                    stderr=""
                )
            if args[:3] == ("ls-remote", "--refs", "origin"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="abc123\tHEAD",
                    stderr=""
                )
            if args[0] == "merge-base":
                # Both ancestry checks fail.
                return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        mock_runner.git = MagicMock(side_effect=git_side_effect)

        first_run.commit_and_push(mock_runner, mock_ui, sample_config)

        # Should have warned, not pushed.
        warn_msgs = [m[1] for m in mock_ui._messages if m[0] == "warn"]
        assert any("don't share history" in m for m in warn_msgs)
        push_calls = [
            c for c in mock_runner.git.call_args_list
            if len(c.args) >= 1 and c.args[0] == "push"
        ]
        assert len(push_calls) == 0
