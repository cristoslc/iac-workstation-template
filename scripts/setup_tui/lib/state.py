"""State detection — determines what setup phase the repo is in."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .runner import REPO_ROOT, ToolRunner

AGE_KEY_PATH = Path.home() / ".config" / "sops" / "age" / "keys.txt"
SOPS_YAML = REPO_ROOT / ".sops.yaml"
SETUP_SH = REPO_ROOT / "setup.sh"
BOOTSTRAP_SH = REPO_ROOT / "bootstrap.sh"
README_MD = REPO_ROOT / "README.md"

# Token that indicates first-run has NOT been performed.
AGE_TOKEN = "${AGE_PUBLIC_KEY}"


@dataclass
class RepoConfig:
    """Collected during first-run, used by token replacement and git ops."""

    age_public_key: str = ""
    github_username: str = ""
    repo_name: str = ""

    @property
    def github_repo_url(self) -> str:
        return f"https://github.com/{self.github_username}/{self.repo_name}.git"


@dataclass
class ResumeState:
    """Result of re-run detection."""

    is_personalized: bool = False
    has_origin: bool = False
    has_commit: bool = False
    is_pushed: bool = False
    has_precommit: bool = False
    has_placeholder_secrets: bool = False
    pending: list[str] = field(default_factory=list)


def detect_resume_state(runner: ToolRunner) -> ResumeState:
    """Check if first-run was already (partially) completed."""
    state = ResumeState()

    sops_content = SOPS_YAML.read_text()
    state.is_personalized = AGE_TOKEN not in sops_content

    if not state.is_personalized:
        return state

    result = runner.git("remote", "get-url", "origin", check=False)
    state.has_origin = result.returncode == 0

    precommit_hook = REPO_ROOT / ".git" / "hooks" / "pre-commit"
    state.has_precommit = precommit_hook.exists()

    diff_result = runner.git(
        "diff", "--quiet", "--", ".sops.yaml", "setup.sh", "bootstrap.sh", "README.md",
        check=False,
    )
    diff_secrets = runner.git(
        "diff", "--quiet", "--", "*/secrets/*", check=False
    )
    state.has_commit = diff_result.returncode == 0 and diff_secrets.returncode == 0

    if state.has_origin and state.has_commit:
        rev_parse = runner.git("rev-parse", "--verify", "origin/main", check=False)
        if rev_parse.returncode == 0:
            head = runner.git("rev-parse", "HEAD").stdout.strip()
            origin_main = runner.git("rev-parse", "origin/main").stdout.strip()
            state.is_pushed = head == origin_main

    if not state.has_precommit:
        state.pending.append("install pre-commit hooks")
    if not state.has_origin:
        state.pending.append("set up GitHub remote")
    if not state.has_commit:
        state.pending.append("commit personalized changes")
    if not state.is_pushed:
        state.pending.append("push to remote")

    # Check for placeholder secrets.
    shared_vars = REPO_ROOT / "shared" / "secrets" / "vars.sops.yml"
    if shared_vars.exists():
        raw = shared_vars.read_text()
        if "PLACEHOLDER" in raw:
            state.has_placeholder_secrets = True
        else:
            decrypted = runner.sops_decrypt(shared_vars)
            if "PLACEHOLDER" in decrypted:
                state.has_placeholder_secrets = True

    return state


def extract_resume_config(runner: ToolRunner) -> RepoConfig:
    """Extract RepoConfig from an already-personalized repo."""
    public_key = ""
    if AGE_KEY_PATH.exists():
        public_key = runner.age_public_key_from_file(AGE_KEY_PATH)
    if not public_key:
        public_key = runner.run(
            ["age-keygen", "-y", str(AGE_KEY_PATH)], check=False
        ).stdout.strip()

    repo_url = ""
    setup_content = SETUP_SH.read_text()
    match = re.search(r'https://github\.com/[^"\s]*\.git', setup_content)
    if match:
        repo_url = match.group(0)
    if not repo_url:
        result = runner.git("remote", "get-url", "origin", check=False)
        if result.returncode == 0:
            url = result.stdout.strip()
            url = re.sub(r"git@github\.com:", "https://github.com/", url)
            if not url.endswith(".git"):
                url += ".git"
            repo_url = url

    if not repo_url:
        raise RuntimeError(
            "Could not determine repo info from setup.sh or origin remote."
        )

    path_part = repo_url.split("github.com/", 1)[1].rstrip(".git")
    parts = path_part.split("/")
    username = parts[0] if parts else ""
    repo_name = parts[1] if len(parts) > 1 else ""

    return RepoConfig(
        age_public_key=public_key,
        github_username=username,
        repo_name=repo_name,
    )
