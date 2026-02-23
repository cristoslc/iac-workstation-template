#!/usr/bin/env python3
"""First-run setup: personalizes the template repo, generates age key, encrypts
secrets, and pushes to your own GitHub repo.

Run via: ./first-run.sh (bash shim installs prereqs, then execs this script)
Direct: uv run --with rich,pyyaml scripts/first-run.py [--debug]
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
AGE_KEY_PATH = Path.home() / ".config" / "sops" / "age" / "keys.txt"
SOPS_YAML = REPO_ROOT / ".sops.yaml"
BOOTSTRAP_SH = REPO_ROOT / "bootstrap.sh"
README_MD = REPO_ROOT / "README.md"
FIRST_RUN_LOG = REPO_ROOT / "first-run.log"

# Token that indicates first-run has NOT been performed.
AGE_TOKEN = "${AGE_PUBLIC_KEY}"

logger = logging.getLogger("first-run")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RepoConfig:
    """Collected during Phases 3-4, used by Phases 5-10."""

    age_public_key: str = ""
    github_username: str = ""
    repo_name: str = ""

    @property
    def github_repo_url(self) -> str:
        return f"https://github.com/{self.github_username}/{self.repo_name}.git"


@dataclass
class ResumeState:
    """Result of Phase 2 re-run detection."""

    is_personalized: bool = False
    has_origin: bool = False
    has_commit: bool = False
    is_pushed: bool = False
    has_precommit: bool = False
    has_placeholder_secrets: bool = False
    pending: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FirstRunError(Exception):
    """Base exception for first-run failures."""


class AgeKeyError(FirstRunError):
    """Age key generation or extraction failure."""


class EncryptionError(FirstRunError):
    """SOPS encryption or decryption failure."""


class GitError(FirstRunError):
    """Git operation failure."""


class GitHubError(FirstRunError):
    """GitHub CLI failure."""


# ---------------------------------------------------------------------------
# ToolRunner — testability seam for all subprocess calls
# ---------------------------------------------------------------------------


class ToolRunner:
    """Wraps subprocess calls to external tools. Injectable for testing."""

    def __init__(self, *, debug: bool = False) -> None:
        self.debug = debug

    def run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        capture: bool = True,
        input_text: str | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            env=env,
            input=input_text,
            check=check,
            cwd=cwd,
        )
        if capture:
            if result.stdout.strip():
                logger.debug("stdout: %s", result.stdout.strip())
            if result.stderr.strip():
                logger.debug("stderr: %s", result.stderr.strip())
        return result

    def command_exists(self, cmd: str) -> bool:
        return shutil.which(cmd) is not None

    # --- Age ---

    def age_keygen(self) -> tuple[str, str]:
        """Generate age keypair. Returns (full_output, public_key)."""
        result = self.run(["age-keygen"], capture=True, check=True)
        output = result.stderr + result.stdout
        public_key = ""
        for line in output.splitlines():
            if line.startswith("Public key:"):
                public_key = line.split(":", 1)[1].strip()
                break
        # The private key block goes to stdout.
        private_block = result.stdout.strip()
        return private_block, public_key

    def age_public_key_from_file(self, path: Path) -> str:
        """Extract public key from existing key file."""
        # First try reading it from the file content.
        content = path.read_text()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("age1"):
                return stripped
            if "public key:" in stripped.lower():
                return stripped.split(":", 1)[1].strip()
        # Fall back to age-keygen -y.
        result = self.run(["age-keygen", "-y", str(path)], check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return ""

    # --- SOPS ---

    def sops_encrypt_in_place(self, path: Path) -> None:
        self.run(["sops", "-e", "-i", str(path)], check=True)

    def sops_decrypt(self, path: Path) -> str:
        result = self.run(["sops", "-d", str(path)], check=False)
        if result.returncode != 0:
            return ""
        return result.stdout

    # --- Git ---

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run(["git", "-C", str(REPO_ROOT), *args], check=check)

    # --- GitHub CLI ---

    def gh(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run(["gh", *args], check=check)



# ---------------------------------------------------------------------------
# WizardUI — output + prompts via Rich
# ---------------------------------------------------------------------------


class WizardUI:
    """Styled output and interactive prompts via Rich Console."""

    def __init__(self, console: Console) -> None:
        self.console = console

    def info(self, msg: str) -> None:
        self.console.print(f"[green]\\[INFO][/green] {msg}")
        logger.info(msg)

    def warn(self, msg: str) -> None:
        self.console.print(f"[yellow]\\[WARN][/yellow] {msg}")
        logger.warning(msg)

    def error(self, msg: str) -> None:
        self.console.print(f"[red]\\[ERROR][/red] {msg}")
        logger.error(msg)

    def banner(
        self,
        title: str,
        lines: list[str] | None = None,
        border_style: str = "blue",
    ) -> None:
        content = "\n".join(lines) if lines else ""
        self.console.print(Panel(content, title=title, border_style=border_style))

    def success_banner(self, title: str, lines: list[str]) -> None:
        self.console.print(
            Panel(
                "\n".join(lines),
                title=title,
                border_style="bold green",
                padding=(1, 2),
            )
        )

    # --- Interactive prompts (replaces gum subprocess calls) ---

    def prompt(
        self,
        label: str,
        *,
        default: str = "",
        sensitive: bool = False,
    ) -> str:
        """Prompt for a single-line value. Returns empty string on Enter.

        sensitive: if True, the value is masked in logs (but still visible
        during input so the user can verify paste accuracy).
        """
        suffix = f" [{default}]" if default and not sensitive else ""
        prompt_str = f"  [bold cyan]{label}[/bold cyan]{suffix}: "
        logger.debug("Prompt: %s (default=%r, sensitive=%s)", label, default, sensitive)
        try:
            value = self.console.input(prompt_str)
        except EOFError:
            value = ""
        result = value.strip() or default
        logger.debug("Prompt result: %s", "***" if sensitive else result)
        return result

    def confirm(self, question: str, *, default: bool = False) -> bool:
        """Yes/no confirmation. Returns bool."""
        hint = "[Y/n]" if default else "[y/N]"
        prompt_str = f"  [bold cyan]{question}[/bold cyan] {hint}: "
        logger.debug("Confirm: %s (default=%s)", question, default)
        try:
            answer = self.console.input(prompt_str).strip().lower()
        except EOFError:
            answer = ""
        if not answer:
            return default
        return answer in ("y", "yes")

    def choose(self, header: str, choices: list[str]) -> str:
        """Numbered choice list. Returns the chosen string."""
        self.console.print(f"\n  [bold]{header}[/bold]")
        for i, choice in enumerate(choices, 1):
            self.console.print(f"    [cyan]{i}.[/cyan] {choice}")
        logger.debug("Choose: %s from %r", header, choices)
        while True:
            try:
                answer = self.console.input("  [bold cyan]Choice[/bold cyan]: ").strip()
            except EOFError:
                return choices[-1]  # Default to last (usually Exit).
            if answer.isdigit() and 1 <= int(answer) <= len(choices):
                selected = choices[int(answer) - 1]
                logger.debug("Chose: %s", selected)
                return selected
            self.console.print(f"    [dim]Enter 1-{len(choices)}[/dim]")


# ---------------------------------------------------------------------------
# Phase 2: Detect if already run
# ---------------------------------------------------------------------------


def detect_resume_state(runner: ToolRunner) -> ResumeState:
    """Check if first-run was already (partially) completed."""
    state = ResumeState()

    # Check if .sops.yaml still has the template token.
    sops_content = SOPS_YAML.read_text()
    state.is_personalized = AGE_TOKEN not in sops_content

    if not state.is_personalized:
        return state

    # Check what's incomplete.
    result = runner.git("remote", "get-url", "origin", check=False)
    state.has_origin = result.returncode == 0

    precommit_hook = REPO_ROOT / ".git" / "hooks" / "pre-commit"
    state.has_precommit = precommit_hook.exists()

    # Check if personalization changes are committed.
    diff_result = runner.git(
        "diff", "--quiet", "--", ".sops.yaml", "bootstrap.sh", "README.md",
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
        # Check unencrypted content first (fast path).
        raw = shared_vars.read_text()
        if "PLACEHOLDER" in raw:
            state.has_placeholder_secrets = True
        else:
            # Try decrypting to check.
            decrypted = runner.sops_decrypt(shared_vars)
            if "PLACEHOLDER" in decrypted:
                state.has_placeholder_secrets = True

    return state


def handle_rerun(
    runner: ToolRunner, ui: WizardUI, state: ResumeState
) -> str:
    """Handle re-run scenarios. Returns 'exit', 'edit-secrets', 'resume', or 'restart'."""
    if not state.pending:
        if state.has_placeholder_secrets:
            origin_url = runner.git("remote", "get-url", "origin", check=False).stdout.strip()
            ui.banner(
                "First-run Status",
                [
                    "First-run is complete, but secrets still contain placeholders.",
                    f"  Origin: {origin_url or 'not set'}",
                ],
                border_style="yellow",
            )
            choice = ui.choose(
                "What would you like to do?",
                [
                    "Edit secrets now",
                    "Re-run everything from the beginning",
                    "Exit (edit later with: make edit-secrets-shared)",
                ],
            )
            if choice.startswith("Edit"):
                return "edit-secrets"
            if choice.startswith("Re-run"):
                return "restart"
            return "exit"

        origin_url = runner.git("remote", "get-url", "origin", check=False).stdout.strip()
        ui.banner(
            "First-run Status",
            [
                "First-run is already complete.",
                f"  Origin: {origin_url or 'not set'}",
            ],
            border_style="green",
        )
        if not ui.confirm("Re-run from the beginning anyway?"):
            ui.info("Nothing to do. Exiting.")
            return "exit"
        return "restart"

    pending_list = "\n".join(f"  - {p}" for p in state.pending)
    ui.banner(
        "First-run Status",
        [
            "First-run was started but not finished. Remaining steps:",
            pending_list,
        ],
        border_style="yellow",
    )
    choice = ui.choose(
        "How would you like to proceed?",
        ["Resume from where it left off", "Start over from the beginning", "Exit"],
    )
    if choice.startswith("Resume"):
        return "resume"
    if choice.startswith("Start"):
        return "restart"
    ui.info("Exiting.")
    return "exit"


# ---------------------------------------------------------------------------
# Phase 3: Generate age keypair
# ---------------------------------------------------------------------------


def generate_or_load_age_key(runner: ToolRunner, ui: WizardUI) -> str:
    """Generate age keypair or load existing. Returns public key."""
    if AGE_KEY_PATH.exists():
        ui.info(f"Age key already exists at {AGE_KEY_PATH}")
        public_key = runner.age_public_key_from_file(AGE_KEY_PATH)
        if not public_key:
            raise AgeKeyError(f"Could not extract public key from {AGE_KEY_PATH}")
        ui.info(f"Public key: {public_key}")
        return public_key

    ui.info("Generating age keypair...")
    key_dir = AGE_KEY_PATH.parent
    key_dir.mkdir(parents=True, exist_ok=True)

    private_block, public_key = runner.age_keygen()
    if not public_key:
        raise AgeKeyError("age-keygen did not produce a public key")

    AGE_KEY_PATH.write_text(private_block + "\n")
    key_dir.chmod(0o700)
    AGE_KEY_PATH.chmod(0o600)

    ui.info("Age keypair generated.")
    ui.info(f"Public key: {public_key}")
    ui.console.print()
    ui.console.print(
        "[yellow]Keep your private key safe! Back it up to a secure location.[/yellow]"
    )
    ui.console.print(f"[yellow]Path: {AGE_KEY_PATH}[/yellow]")
    return public_key


# ---------------------------------------------------------------------------
# Phase 4: Prompt for GitHub info
# ---------------------------------------------------------------------------


def collect_repo_info(ui: WizardUI) -> RepoConfig:
    """Prompt for GitHub username and repo name."""
    ui.console.print()
    username = ui.prompt("GitHub username")
    repo_name = ui.prompt("Repository name", default="my-workstation")
    config = RepoConfig(github_username=username, repo_name=repo_name)
    ui.info(f"Repo URL: {config.github_repo_url}")
    return config


# ---------------------------------------------------------------------------
# Phase 5: Replace tokens (pure Python — no envsubst)
# ---------------------------------------------------------------------------


def replace_tokens(config: RepoConfig, ui: WizardUI) -> None:
    """Replace template tokens in config files."""
    ui.console.print()
    ui.info("Personalizing configuration files...")

    replacements: dict[Path, dict[str, str]] = {
        SOPS_YAML: {"${AGE_PUBLIC_KEY}": config.age_public_key},
        BOOTSTRAP_SH: {"${GITHUB_REPO_URL}": config.github_repo_url},
        README_MD: {
            "${GITHUB_REPO_URL}": config.github_repo_url,
            "${GITHUB_USERNAME}": config.github_username,
            "${REPO_NAME}": config.repo_name,
        },
    }

    for filepath, tokens in replacements.items():
        content = filepath.read_text()
        for token, value in tokens.items():
            content = content.replace(token, value)
        filepath.write_text(content)
        if filepath == BOOTSTRAP_SH:
            filepath.chmod(0o755)

    ui.info("Tokens replaced in .sops.yaml, bootstrap.sh, and README.md")


# ---------------------------------------------------------------------------
# Phase 6: Encrypt placeholder secret files
# ---------------------------------------------------------------------------


def encrypt_secret_files(runner: ToolRunner, ui: WizardUI) -> int:
    """Find and encrypt all plaintext SOPS files. Returns count encrypted."""
    ui.console.print()
    ui.info("Encrypting secret placeholder files...")

    encrypted_count = 0
    patterns = ["**/*.sops.yml", "**/*.sops.yaml", "**/*.sops"]

    for pattern in patterns:
        for sops_file in REPO_ROOT.glob(pattern):
            # Must be inside a secrets/ directory.
            if "/secrets/" not in str(sops_file):
                continue
            # Skip .decrypted/ directories.
            if "/.decrypted/" in str(sops_file):
                continue
            # Skip already encrypted files (contain sops metadata).
            content = sops_file.read_text()
            if '"sops":' in content or "\nsops:" in content or content.startswith("sops:"):
                ui.info(f"  Already encrypted: {sops_file.relative_to(REPO_ROOT)}")
                continue

            ui.info(f"  Encrypting: {sops_file.relative_to(REPO_ROOT)}")
            runner.sops_encrypt_in_place(sops_file)
            encrypted_count += 1

    ui.info(f"Encrypted {encrypted_count} file(s).")
    return encrypted_count


# ---------------------------------------------------------------------------
# Helper: write + encrypt
# ---------------------------------------------------------------------------


def write_and_encrypt(
    runner: ToolRunner, target: Path, content: str, ui: WizardUI
) -> None:
    """Write plaintext to temp file in target's directory, encrypt, move atomically.

    Temp file MUST be in the target's directory so it matches .sops.yaml's
    path_regex: '.*/secrets/.*'.
    """
    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    fd, tmppath = tempfile.mkstemp(prefix=".tmp.", dir=str(target_dir))
    try:
        os.write(fd, (content + "\n").encode())
        os.close(fd)
        runner.sops_encrypt_in_place(Path(tmppath))
        Path(tmppath).rename(target)
        ui.info(f"Encrypted {target.name}")
    except Exception:
        Path(tmppath).unlink(missing_ok=True)
        ui.error(f"Failed to encrypt {target.name}. Plaintext was NOT written.")
        raise EncryptionError(f"Failed to encrypt {target.name}")


# ---------------------------------------------------------------------------
# Phase 7: Install pre-commit hooks
# ---------------------------------------------------------------------------


def install_precommit(runner: ToolRunner, ui: WizardUI) -> None:
    """Install pre-commit and hooks."""
    ui.console.print()
    if runner.command_exists("pre-commit"):
        ui.info("pre-commit already installed.")
    else:
        ui.info("Installing pre-commit...")
        if runner.command_exists("uv"):
            runner.run(["uv", "tool", "install", "pre-commit"])
        elif runner.command_exists("pip3"):
            runner.run(["pip3", "install", "--user", "pre-commit"])
        else:
            raise FirstRunError(
                "Neither uv nor pip3 available. Cannot install pre-commit."
            )

    # Verify installation.
    if not runner.command_exists("pre-commit"):
        raise FirstRunError(
            "pre-commit installation failed. Cannot continue without "
            "secret-leak protection."
        )

    git_dir = REPO_ROOT / ".git"
    if git_dir.is_dir():
        ui.info("Installing pre-commit hooks...")
        runner.run(["pre-commit", "install"], cwd=REPO_ROOT)
        hook_file = git_dir / "hooks" / "pre-commit"
        if not hook_file.exists():
            raise FirstRunError(
                "pre-commit hook not installed into .git/hooks/. Fix and re-run."
            )


# ---------------------------------------------------------------------------
# Phase 8: Detach from template repo
# ---------------------------------------------------------------------------


def detach_from_template(
    runner: ToolRunner, ui: WizardUI, config: RepoConfig
) -> None:
    """Remove or replace origin if it points to template repo."""
    ui.console.print()
    result = runner.git("remote", "get-url", "origin", check=False)
    if result.returncode != 0:
        return  # No origin set — nothing to detach from.

    current_origin = result.stdout.strip()
    expected_slug = f"{config.github_username}/{config.repo_name}"
    if expected_slug in current_origin:
        ui.info(f"Remote 'origin' already points to {expected_slug}.")
        return

    ui.warn(f"Current origin ({current_origin}) does not match {expected_slug}.")
    if ui.confirm("Replace origin remote?"):
        runner.git("remote", "remove", "origin")
    else:
        ui.info("Keeping existing origin.")


# ---------------------------------------------------------------------------
# Phase 9: Create GitHub repo
# ---------------------------------------------------------------------------


def create_github_repo(
    runner: ToolRunner, ui: WizardUI, config: RepoConfig
) -> None:
    """Create GitHub repo via gh CLI."""
    ui.console.print()
    origin_check = runner.git("remote", "get-url", "origin", check=False)
    if origin_check.returncode == 0:
        ui.info(f"Remote 'origin' already set to: {origin_check.stdout.strip()}")
        return

    slug = f"{config.github_username}/{config.repo_name}"
    if not ui.confirm(f"Create GitHub repo {slug}?"):
        ui.info("Skipping GitHub repo creation.")
        ui.info(f"You can add a remote later with:")
        ui.info(f"  git remote add origin {config.github_repo_url}")
        return

    # Ensure gh is authenticated.
    auth_check = runner.gh("auth", "status", check=False)
    if auth_check.returncode != 0:
        ui.info("GitHub CLI needs authentication...")
        runner.run(["gh", "auth", "login"], capture=False)

    visibility = "--private"
    if ui.confirm("Make the repo public? (Default: private)"):
        visibility = "--public"

    # Check if repo already exists.
    repo_check = runner.gh("repo", "view", slug, check=False)
    if repo_check.returncode == 0:
        ui.info(f"GitHub repo {slug} already exists.")
        runner.git("remote", "add", "origin", config.github_repo_url)
    else:
        ui.info("Creating GitHub repo...")
        runner.gh(
            "repo", "create", slug, visibility,
            "--source", str(REPO_ROOT), "--remote", "origin",
        )

    ui.info(f"Remote set to: {config.github_repo_url}")


# ---------------------------------------------------------------------------
# Phase 10: Commit + push
# ---------------------------------------------------------------------------


def commit_and_push(
    runner: ToolRunner, ui: WizardUI, config: RepoConfig
) -> None:
    """Stage, commit, push with merge-base safety check."""
    ui.console.print()
    if not ui.confirm("Commit personalized changes and push?"):
        ui.info("Skipping commit. You can commit later with:")
        ui.info("  git add -u && git commit -m 'Initialize personalized workstation config'")
        return

    # Initialize git if needed.
    git_dir = REPO_ROOT / ".git"
    if not git_dir.is_dir():
        runner.git("init")
        runner.git("branch", "-M", "main")

    # Stage tracked files + the specific files modified by token replacement/sops.
    runner.git("add", "-u")
    runner.git("add", ".sops.yaml", "bootstrap.sh", "README.md")

    # Check if there are staged changes.
    diff_check = runner.git("diff", "--cached", "--quiet", check=False)
    if diff_check.returncode == 0:
        ui.info("Nothing to commit (already personalized).")
    else:
        runner.git("commit", "-m", "Initialize personalized workstation config")

    # Push if origin is set.
    origin_check = runner.git("remote", "get-url", "origin", check=False)
    if origin_check.returncode != 0:
        ui.info("Committed locally. Push when you've added a remote.")
        return

    origin_url = origin_check.stdout.strip()

    # Safety check: verify remote shares our history.
    ls_remote = runner.git("ls-remote", "--refs", "origin", "HEAD", check=False)
    remote_head = ""
    if ls_remote.returncode == 0 and ls_remote.stdout.strip():
        remote_head = ls_remote.stdout.strip().split()[0]

    if remote_head:
        # Check ancestry in both directions.
        ancestor_check1 = runner.git(
            "merge-base", "--is-ancestor", remote_head, "HEAD", check=False
        )
        ancestor_check2 = runner.git(
            "merge-base", "--is-ancestor", "HEAD", remote_head, check=False
        )
        if ancestor_check1.returncode == 0 or ancestor_check2.returncode == 0:
            _try_push(runner, ui, origin_url)
        else:
            ui.warn("Remote has commits that don't share history with this repo.")
            ui.warn("Refusing to push. Verify that origin points to the correct repo.")
            ui.warn(f"  origin: {origin_url}")
    else:
        # Empty remote — first push.
        _try_push(runner, ui, origin_url)


def _try_push(runner: ToolRunner, ui: WizardUI, origin_url: str) -> None:
    """Attempt git push, warn on failure instead of aborting."""
    result = runner.git("push", "-u", "origin", "main", check=False)
    if result.returncode == 0:
        ui.info(f"Pushed to {origin_url}")
    else:
        ui.warn("Push failed. You can push manually later with: git push -u origin main")
        stderr = result.stderr.strip() if result.stderr else ""
        if "workflow" in stderr:
            ui.warn(
                "Hint: GitHub rejected the push because your token lacks the "
                "'workflow' scope (needed for .github/workflows/ changes)."
            )
            ui.warn("Fix with: gh auth refresh -s workflow")
        elif stderr:
            ui.warn(f"  {stderr}")


# ---------------------------------------------------------------------------
# Phase 11: Guided secret editing
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Secret schema: what the system needs
# ---------------------------------------------------------------------------


@dataclass
class SecretField:
    """One secret the system consumes."""

    key: str              # Variable name (git_user_email, ANTHROPIC_API_KEY, ...)
    label: str            # Human-readable label for the prompt
    placeholder: str      # Example value shown in empty field
    description: str      # What this secret is used for
    used_by: str          # Which roles/tools consume this secret
    doc_url: str = ""     # URL to docs on how to obtain this secret
    password: bool = False  # Mask input


# Ansible vars — written to vars.sops.yml as YAML key/value pairs.
SHARED_ANSIBLE_VARS: list[SecretField] = [
    SecretField(
        key="git_user_email",
        label="Git email",
        placeholder="you@example.com",
        description="Sets git config user.email globally",
        used_by="git role",
    ),
    SecretField(
        key="git_user_name",
        label="Git display name",
        placeholder="Your Name",
        description="Sets git config user.name globally",
        used_by="git role",
    ),
]

# Shell secrets — written to secrets.zsh.sops as export statements.
# Sourced by .zshrc via ~/.config/zsh/secrets.zsh.
SHELL_SECRETS: list[SecretField] = [
    SecretField(
        key="ANTHROPIC_API_KEY",
        label="Anthropic API key",
        placeholder="sk-ant-...",
        description="API access for Claude CLI and SDK",
        used_by="claude-code role, Claude CLI",
        doc_url="https://console.anthropic.com/settings/keys",
        password=True,
    ),
    SecretField(
        key="HOMEBREW_GITHUB_API_TOKEN",
        label="GitHub token for Homebrew",
        placeholder="ghp_...",
        description="Avoids GitHub API rate limits during brew install",
        used_by="homebrew role (macOS)",
        doc_url="https://github.com/settings/tokens",
        password=True,
    ),
]


def _show_secret_overview(ui: WizardUI, plat: str) -> None:
    """Print a table of all secrets the wizard will prompt for."""
    table = Table(
        title="Secrets Overview",
        show_header=True,
        header_style="bold",
        border_style="cyan",
        pad_edge=False,
        show_lines=True,
    )
    table.add_column("#", style="cyan", width=3, justify="right")
    table.add_column("Variable", style="bold")
    table.add_column("Purpose")
    table.add_column("Used By", style="dim italic")
    table.add_column("Docs", style="dim")

    n = 0
    for sf in SHARED_ANSIBLE_VARS:
        n += 1
        doc_cell = f"[link={sf.doc_url}]{sf.doc_url}[/link]" if sf.doc_url else ""
        table.add_row(str(n), sf.key, sf.description, sf.used_by, doc_cell)
    for sf in SHELL_SECRETS:
        n += 1
        doc_cell = f"[link={sf.doc_url}]{sf.doc_url}[/link]" if sf.doc_url else ""
        table.add_row(str(n), sf.key, sf.description, sf.used_by, doc_cell)

    ui.console.print()
    ui.console.print(table)
    ui.console.print()
    ui.console.print(
        "  [dim]Press Enter to skip any value. "
        "Edit later with: make edit-secrets-shared[/dim]"
    )
    ui.console.print(
        "  [dim]Shell secrets are encrypted in the repo, decrypted at bootstrap,"
        " and sourced via ~/.config/zsh/secrets.zsh[/dim]"
    )


def _mask_value(value: str) -> str:
    """Show first 4 and last 4 chars of a secret for confirmation."""
    if len(value) <= 10:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def _prompt_for_field(
    ui: WizardUI, sf: SecretField, current: str = ""
) -> str:
    """Prompt for a single secret field with context and confirmation."""
    ui.console.print()
    ui.console.print(f"  [bold]{sf.label}[/bold] [dim]({sf.key})[/dim]")
    ui.console.print(f"  [dim]{sf.description} \u2014 used by: {sf.used_by}[/dim]")
    if sf.doc_url:
        ui.console.print(f"  [dim]Docs:[/dim] [link={sf.doc_url}]{sf.doc_url}[/link]")

    label = sf.label
    if current and not sf.password:
        label += f" [{current}]"
    elif current and sf.password:
        label += f" [current: {_mask_value(current)}]"

    value = ui.prompt(label, default=current, sensitive=sf.password)

    # Show masked confirmation so the user can verify what was captured.
    if value and sf.password:
        ui.console.print(
            f"  [green]\u2713[/green] [dim]Saved: {_mask_value(value)} "
            f"({len(value)} chars)[/dim]"
        )

    return value


def edit_secrets(
    runner: ToolRunner, ui: WizardUI, plat: str
) -> None:
    """Walk the user through each secret the system needs."""
    ui.console.print()
    ui.banner(
        "Secret Configuration",
        [
            "The wizard will walk you through each secret the system uses.",
            "Values are SOPS-encrypted before being stored in the repo.",
        ],
        border_style="cyan",
    )

    # Show overview table so the user knows what's coming.
    _show_secret_overview(ui, plat)

    # --- Shared Ansible vars (vars.sops.yml) ---
    ui.console.print()
    ui.console.print("  [bold underline]Ansible Variables[/bold underline]")

    shared_vars = REPO_ROOT / "shared" / "secrets" / "vars.sops.yml"

    # Load existing values so we can pre-fill prompts.
    current_values: dict[str, str] = {}
    if shared_vars.exists():
        decrypted = runner.sops_decrypt(shared_vars)
        for line in decrypted.splitlines():
            if ":" in line and not line.startswith("#") and not line.startswith("---"):
                key, _, val = line.partition(":")
                val = val.strip().strip("'\"")
                if val and val != "PLACEHOLDER":
                    current_values[key.strip()] = val

    # Prompt for each declared Ansible var.
    collected_vars: dict[str, str] = {}
    for sf in SHARED_ANSIBLE_VARS:
        current = current_values.get(sf.key, "")
        value = _prompt_for_field(ui, sf, current)
        collected_vars[sf.key] = value or "PLACEHOLDER"
        if value:
            ui.info(f"  {sf.key}: {value}")
        else:
            ui.info(f"  {sf.key}: skipped")

    # Write vars.sops.yml with all collected values.
    yaml_lines = ["---"]
    for key, value in collected_vars.items():
        yaml_lines.append(f'{key}: "{value}"')
    write_and_encrypt(runner, shared_vars, "\n".join(yaml_lines), ui)

    # --- Shell secrets (secrets.zsh.sops) ---
    ui.console.print()
    ui.console.print("  [bold underline]Shell Secrets[/bold underline]")

    shell_file = (
        REPO_ROOT / "shared" / "secrets" / "dotfiles" / "zsh"
        / ".config" / "zsh" / "secrets.zsh.sops"
    )

    # Load existing exports so we can pre-fill and preserve custom ones.
    existing_exports: dict[str, str] = {}
    if shell_file.exists():
        existing = runner.sops_decrypt(shell_file)
        if existing:
            for line in existing.splitlines():
                if line.startswith("export "):
                    eq_pos = line.find("=")
                    if eq_pos > 0:
                        ekey = line[len("export "):eq_pos]
                        eval_ = line[eq_pos + 1:].strip().strip('"')
                        existing_exports[ekey] = eval_

    # Prompt for each declared shell secret.
    collected_exports: dict[str, str] = dict(existing_exports)
    for sf in SHELL_SECRETS:
        current = existing_exports.get(sf.key, "")
        value = _prompt_for_field(ui, sf, current)
        if value:
            collected_exports[sf.key] = value
            ui.info(f"  {sf.key}: set")
        elif not current:
            ui.info(f"  {sf.key}: skipped")

    # Offer to add custom secrets beyond the declared ones.
    ui.console.print()
    while ui.confirm("Add a custom shell secret not listed above?"):
        custom_key = ui.prompt("Variable name")
        if not custom_key:
            continue
        custom_value = ui.prompt(f"Value for {custom_key}", sensitive=True)
        if not custom_value:
            ui.info(f"  Skipped {custom_key} (empty value).")
            continue
        collected_exports[custom_key] = custom_value
        ui.info(
            f"  {custom_key}: saved "
            f"({_mask_value(custom_value)}, {len(custom_value)} chars)"
        )

    # Write secrets.zsh.sops.
    if collected_exports:
        lines = ["# Shell secrets -- sourced by .zshrc"]
        for ekey, eval_ in collected_exports.items():
            lines.append(f'export {ekey}="{eval_}"')
        write_and_encrypt(runner, shell_file, "\n".join(lines), ui)
    else:
        ui.info("No shell secrets configured.")

    # --- Platform vars ---
    ui.console.print()
    if plat == "macos":
        ui.info("macOS secrets: no platform-specific keys defined yet.")
    else:
        ui.info("Linux secrets: no platform-specific keys defined yet.")

    # --- Summary ---
    ui.console.print()
    ui.info("To edit secrets later:")
    ui.info("  make edit-secrets-shared    # Ansible vars + shell secrets")
    if plat == "macos":
        ui.info("  make edit-secrets-macos     # macOS-specific vars")
    else:
        ui.info("  make edit-secrets-linux     # Linux-specific vars")
    ui.info("  Tip: EDITOR=nano make edit-secrets-shared")


# ---------------------------------------------------------------------------
# Resume: extract config from already-personalized repo
# ---------------------------------------------------------------------------


def extract_resume_config(runner: ToolRunner, ui: WizardUI) -> RepoConfig:
    """Extract RepoConfig from an already-personalized repo."""
    # Extract public key from age key file.
    public_key = ""
    if AGE_KEY_PATH.exists():
        public_key = runner.age_public_key_from_file(AGE_KEY_PATH)
    if not public_key:
        public_key = runner.run(
            ["age-keygen", "-y", str(AGE_KEY_PATH)], check=False
        ).stdout.strip()

    # Extract repo URL from bootstrap.sh or origin.
    repo_url = ""
    bootstrap_content = BOOTSTRAP_SH.read_text()
    import re
    match = re.search(r'https://github\.com/[^"\s]*\.git', bootstrap_content)
    if match:
        repo_url = match.group(0)
    if not repo_url:
        result = runner.git("remote", "get-url", "origin", check=False)
        if result.returncode == 0:
            url = result.stdout.strip()
            # Normalize SSH to HTTPS.
            url = re.sub(r"git@github\.com:", "https://github.com/", url)
            if not url.endswith(".git"):
                url += ".git"
            repo_url = url

    if not repo_url:
        raise GitError("Could not determine repo info from bootstrap.sh or origin remote.")

    # Parse username/repo from URL.
    path_part = repo_url.split("github.com/", 1)[1].rstrip(".git")
    parts = path_part.split("/")
    username = parts[0] if parts else ""
    repo_name = parts[1] if len(parts) > 1 else ""

    config = RepoConfig(
        age_public_key=public_key,
        github_username=username,
        repo_name=repo_name,
    )
    ui.info(f"Resuming: {username}/{repo_name}")
    return config


# ---------------------------------------------------------------------------
# Completion banner
# ---------------------------------------------------------------------------


def show_completion(ui: WizardUI, config: RepoConfig) -> None:
    ui.console.print()
    ui.success_banner(
        "First-run complete!",
        [
            "Next steps:",
            "  1. Transfer age key to another machine:",
            "     make key-send      (here -- uses Magic Wormhole)",
            "     make key-receive   (there)",
            "  2. On the new machine:",
            f"     git clone {config.github_repo_url} ~/.workstation",
            "     cd ~/.workstation && make key-receive",
            "     ./bootstrap.sh",
            "",
            f"Log: {FIRST_RUN_LOG}",
        ],
    )


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging(*, debug: bool) -> None:
    """Configure dual logging: file (always DEBUG) + console (INFO or DEBUG)."""
    root_logger = logging.getLogger("first-run")
    root_logger.setLevel(logging.DEBUG)

    # File handler — always captures everything.
    fh = logging.FileHandler(str(FIRST_RUN_LOG), mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s")
    )
    root_logger.addHandler(fh)

    # Console handler — only for debug mode (Rich handles normal output).
    if debug:
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(logging.Formatter("[DEBUG] %(message)s"))
        root_logger.addHandler(ch)

    # Log header.
    root_logger.info(
        "first-run.py -- %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
    )
    root_logger.info("platform: %s %s", platform.system(), platform.machine())
    root_logger.info("python: %s", sys.version.split()[0])
    root_logger.info("debug: %s", debug)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="First-run template personalization wizard"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Restrict file creation to owner-only (defense-in-depth).
    os.umask(0o077)

    setup_logging(debug=args.debug)

    # Platform detection (shim exports PLATFORM; fallback to detection).
    plat = os.environ.get("PLATFORM") or (
        "macos" if sys.platform == "darwin" else "linux"
    )

    # SOPS age key file (macOS uses ~/Library/Application Support/ by default;
    # we use ~/.config/ per XDG convention).
    os.environ["SOPS_AGE_KEY_FILE"] = str(AGE_KEY_PATH)

    console = Console()
    ui = WizardUI(console)
    runner = ToolRunner(debug=args.debug)

    try:
        # Phase 2: Resume detection.
        state = detect_resume_state(runner)

        if state.is_personalized:
            action = handle_rerun(runner, ui, state)
            if action == "exit":
                return
            if action == "edit-secrets":
                edit_secrets(runner, ui, plat)
                return
            resume = action == "resume"
        else:
            resume = False

        if resume:
            config = extract_resume_config(runner, ui)
        else:
            # Phase 3: Age key.
            console.print()
            ui.banner("First-Run Setup")
            age_pub = generate_or_load_age_key(runner, ui)

            # Phase 4: Repo info.
            config = collect_repo_info(ui)
            config.age_public_key = age_pub

            # Phase 5: Token replacement.
            replace_tokens(config, ui)

            # Phase 6: Encrypt secrets.
            encrypt_secret_files(runner, ui)

        # Phase 7: Pre-commit (always — idempotent).
        install_precommit(runner, ui)

        # Phase 8: Detach from template.
        detach_from_template(runner, ui, config)

        # Phase 9: Create GitHub repo.
        create_github_repo(runner, ui, config)

        # Phase 10: Commit + push.
        commit_and_push(runner, ui, config)

        # Phase 11: Secrets.
        edit_secrets(runner, ui, plat)

        # Done.
        show_completion(ui, config)

    except KeyboardInterrupt:
        ui.warn("Interrupted. Re-run ./first-run.sh to continue.")
        sys.exit(130)
    except FirstRunError as e:
        ui.error(str(e))
        ui.error(f"Check {FIRST_RUN_LOG} for details.")
        logger.exception("First-run error")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        cmd_str = " ".join(e.cmd) if isinstance(e.cmd, list) else e.cmd
        ui.error(f"Command failed: {cmd_str}")
        if e.stderr:
            ui.error(e.stderr.strip())
        ui.error(f"Check {FIRST_RUN_LOG} for details.")
        logger.exception("Command failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
