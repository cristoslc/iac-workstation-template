"""Git and GitHub operations."""

from __future__ import annotations

import logging

from .runner import REPO_ROOT, ToolRunner
from .state import RepoConfig

logger = logging.getLogger("setup")


class GitError(Exception):
    """Git operation failure."""


class GitHubError(Exception):
    """GitHub CLI failure."""


def _preferred_remote_url(runner: ToolRunner, config: RepoConfig) -> str:
    """Return the remote URL matching the gh auth git protocol.

    If ``gh auth status`` reports SSH, return an SSH URL; otherwise fall back
    to the HTTPS URL from *config*.
    """
    result = runner.gh("auth", "status", check=False)
    output = (result.stdout or "") + (result.stderr or "")
    if "git_protocol: ssh" in output or "Git operations protocol: ssh" in output:
        return f"git@github.com:{config.github_username}/{config.repo_name}.git"
    return config.github_repo_url


def detach_from_template(runner: ToolRunner, config: RepoConfig) -> str | None:
    """Check if origin points to template repo.

    Returns a message if action was taken, or None if no change needed.
    """
    result = runner.git("remote", "get-url", "origin", check=False)
    if result.returncode != 0:
        return None

    current_origin = result.stdout.strip()
    expected_slug = f"{config.github_username}/{config.repo_name}"
    if expected_slug in current_origin:
        return f"Remote 'origin' already points to {expected_slug}."

    return f"Current origin ({current_origin}) does not match {expected_slug}."


def remove_origin(runner: ToolRunner) -> None:
    """Remove the origin remote."""
    runner.git("remote", "remove", "origin")


def create_github_repo(
    runner: ToolRunner, config: RepoConfig, *, public: bool = False
) -> list[str]:
    """Create GitHub repo via gh CLI. Returns status messages."""
    messages = []
    slug = f"{config.github_username}/{config.repo_name}"

    # Ensure gh is authenticated.
    auth_check = runner.gh("auth", "status", check=False)
    if auth_check.returncode != 0:
        runner.run(["gh", "auth", "login"], capture=False)

    visibility = "--public" if public else "--private"

    remote_url = _preferred_remote_url(runner, config)

    # Check if repo already exists.
    repo_check = runner.gh("repo", "view", slug, check=False)
    if repo_check.returncode == 0:
        messages.append(f"GitHub repo {slug} already exists.")
        runner.git("remote", "add", "origin", remote_url)
    else:
        messages.append("Creating GitHub repo...")
        runner.gh(
            "repo", "create", slug, visibility,
            "--source", str(REPO_ROOT), "--remote", "origin",
        )

    messages.append(f"Remote set to: {remote_url}")
    return messages


def commit_and_push(runner: ToolRunner) -> list[str]:
    """Stage, commit, push with merge-base safety check. Returns status messages."""
    messages = []

    # Initialize git if needed.
    git_dir = REPO_ROOT / ".git"
    if not git_dir.is_dir():
        runner.git("init")
        runner.git("branch", "-M", "main")

    runner.git("add", "-u")
    runner.git("add", ".sops.yaml", "setup.sh", "bootstrap.sh", "README.md")

    diff_check = runner.git("diff", "--cached", "--quiet", check=False)
    if diff_check.returncode == 0:
        messages.append("Nothing to commit (already personalized).")
    else:
        runner.git("commit", "-m", "Initialize personalized workstation config")
        messages.append("Committed personalized changes.")

    # Push if origin is set.
    origin_check = runner.git("remote", "get-url", "origin", check=False)
    if origin_check.returncode != 0:
        messages.append("Committed locally. Push when you've added a remote.")
        return messages

    origin_url = origin_check.stdout.strip()

    # Safety check: verify remote shares our history.
    ls_remote = runner.git("ls-remote", "--refs", "origin", "HEAD", check=False)
    remote_head = ""
    if ls_remote.returncode == 0 and ls_remote.stdout.strip():
        remote_head = ls_remote.stdout.strip().split()[0]

    if remote_head:
        ancestor_check1 = runner.git(
            "merge-base", "--is-ancestor", remote_head, "HEAD", check=False
        )
        ancestor_check2 = runner.git(
            "merge-base", "--is-ancestor", "HEAD", remote_head, check=False
        )
        if ancestor_check1.returncode == 0 or ancestor_check2.returncode == 0:
            messages.extend(_try_push(runner, origin_url))
        else:
            messages.append(
                "Remote has commits that don't share history with this repo. "
                "Refusing to push."
            )
    else:
        messages.extend(_try_push(runner, origin_url))

    return messages


def _try_push(runner: ToolRunner, origin_url: str) -> list[str]:
    """Attempt git push, return status messages."""
    messages = []
    result = runner.git("push", "-u", "origin", "main", check=False)
    if result.returncode == 0:
        messages.append(f"Pushed to {origin_url}")
    else:
        messages.append("Push failed. You can push manually: git push -u origin main")
        stderr = result.stderr.strip() if result.stderr else ""
        if "workflow" in stderr:
            messages.append(
                "Hint: GitHub rejected the push because your token lacks the "
                "'workflow' scope. Fix with: gh auth refresh -s workflow"
            )
        elif stderr:
            messages.append(f"  {stderr}")
    return messages
