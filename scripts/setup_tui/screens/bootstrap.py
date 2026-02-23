"""BootstrapScreen — mode/phase selection, prereqs, and ansible execution."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    RadioButton,
    RadioSet,
    RichLog,
    SelectionList,
    Static,
)

from ..lib.runner import REPO_ROOT

logger = logging.getLogger("setup")

BOOTSTRAP_LOG = REPO_ROOT / "bootstrap.log"
ANSIBLE_LOG = Path.home() / ".local" / "log" / "ansible.log"

# Phase definitions — order matches site.yml playbook imports.
PHASES = [
    ("system", "System", "OS packages, fonts, system settings"),
    ("security", "Security", "SSH keys, GPG, firewall, disk encryption checks"),
    ("dev-tools", "Dev Tools", "Languages, editors, CLI tools, containers"),
    ("desktop", "Desktop", "Window manager, terminal, theme, apps"),
    ("dotfiles", "Dotfiles", "Shell config, git config, app settings via stow"),
]

# Phases selected by default for each mode.
DEFAULT_PHASES = {
    "fresh": ["system", "security", "dev-tools", "desktop", "dotfiles"],
    "new_account": ["security", "dev-tools", "desktop", "dotfiles"],
    "existing_account": ["security", "dev-tools", "desktop", "dotfiles"],
}


class BootstrapModeScreen(Screen):
    """Step 1: Select bootstrap mode."""

    BINDINGS = [("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-content"):
            yield Static(
                "[bold]Bootstrap — Step 1 of 3[/bold]\n\n"
                "What kind of system is this?\n"
                "[dim]Arrow keys to choose, Tab to reach Next, Enter to press[/dim]"
            )
            with RadioSet(id="mode-select"):
                yield RadioButton(
                    "Existing system, existing user account",
                    id="existing_account",
                    value=True,
                )
                yield RadioButton(
                    "Existing system, new user account",
                    id="new_account",
                )
                yield RadioButton(
                    "Fresh install (new OS, clean slate)",
                    id="fresh",
                )
            yield Button("Next", id="next", variant="primary")
        yield Footer()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            radio_set = self.query_one("#mode-select", RadioSet)
            pressed = radio_set.pressed_button
            if pressed is None:
                return
            mode = pressed.id
            self.app.push_screen(BootstrapPhaseScreen(mode))


class BootstrapPhaseScreen(Screen):
    """Step 2: Select which phases to run."""

    BINDINGS = [("escape", "go_back", "Back")]

    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode

    def compose(self) -> ComposeResult:
        defaults = DEFAULT_PHASES.get(self.mode, [])
        yield Header()
        with Vertical(id="main-content"):
            yield Static(
                "[bold]Bootstrap — Step 2 of 3[/bold]\n\n"
                "Which role groups should run?\n"
                "[dim]Arrow keys to move, Space to toggle, Tab to jump to Next[/dim]"
            )
            yield SelectionList[str](
                *[
                    (f"{label}  [dim]{description}[/dim]", phase_id, phase_id in defaults)
                    for phase_id, label, description in PHASES
                ],
                id="phase-list",
            )
            yield Button("Next", id="next", variant="primary")
        yield Footer()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            phase_list = self.query_one("#phase-list", SelectionList)
            selected = list(phase_list.selected)
            if not selected:
                return
            self.app.push_screen(
                BootstrapPasswordScreen(self.mode, selected)
            )


class BootstrapPasswordScreen(Screen):
    """Step 3: Collect sudo password for ansible-playbook --become."""

    BINDINGS = [("escape", "go_back", "Back")]

    def __init__(self, mode: str, phases: list[str]) -> None:
        super().__init__()
        self.mode = mode
        self.phases = phases

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-content"):
            mode_labels = {
                "fresh": "Fresh install",
                "new_account": "New user account",
                "existing_account": "Existing user account",
            }
            phase_labels = {pid: label for pid, label, _ in PHASES}
            phase_names = ", ".join(
                phase_labels.get(p, p) for p in self.phases
            )
            yield Static(
                "[bold]Bootstrap — Step 3 of 3[/bold]\n\n"
                f"[dim]Mode:[/dim]   {mode_labels.get(self.mode, self.mode)}\n"
                f"[dim]Phases:[/dim] {phase_names}\n\n"
                "Enter your sudo password for Ansible privilege escalation.\n"
                "[dim]This is passed to ansible-playbook via environment variable "
                "and is never written to disk.[/dim]\n"
                "[dim]Enter to submit, or Tab to reach Run Bootstrap[/dim]"
            )
            yield Input(
                placeholder="sudo password",
                password=True,
                id="sudo-password",
            )
            yield Static("", id="password-error")
            yield Button("Run Bootstrap", id="run", variant="primary")
        yield Footer()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self._start_run()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            self._start_run()

    def _start_run(self) -> None:
        password = self.query_one("#sudo-password", Input).value
        if not password:
            return
        # Disable controls while validating.
        self.query_one("#run", Button).disabled = True
        self.query_one("#sudo-password", Input).disabled = True
        self.query_one("#password-error", Static).update(
            "[dim]Verifying sudo password… "
            "(may take ~15 s if fingerprint auth is active)[/dim]"
        )
        self._validate_sudo(password)

    @work(thread=True)
    def _validate_sudo(self, password: str) -> None:
        """Test the sudo password before starting the bootstrap run.

        pam_fprintd (if present) blocks for up to 15 s waiting for a
        fingerprint before falling through to pam_unix.  We use a 20 s
        timeout so the password is still validated correctly.
        """
        try:
            proc = subprocess.run(
                ["sudo", "-kS", "true"],
                input=password + "\n",
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.returncode == 0:
                logger.debug("Sudo password validated successfully")
                self.app.call_from_thread(
                    self.app.push_screen,
                    BootstrapRunScreen(self.mode, self.phases, password),
                )
            else:
                logger.warning("Sudo password validation failed (exit %d)", proc.returncode)
                self.app.call_from_thread(self._show_password_error)
        except subprocess.TimeoutExpired:
            # Even 20 s wasn't enough — proceed anyway and let
            # ansible-playbook validate the password at runtime.
            logger.warning(
                "Sudo validation timed out after 20 s; skipping validation"
            )
            self.app.call_from_thread(self._show_timeout_warning, password)

    def _show_password_error(self) -> None:
        """Reset the form and show an error message for wrong password."""
        self.query_one("#password-error", Static).update(
            "[bold red]Wrong password.[/bold red] Please try again."
        )
        password_input = self.query_one("#sudo-password", Input)
        password_input.value = ""
        password_input.disabled = False
        password_input.focus()
        self.query_one("#run", Button).disabled = False

    def _show_timeout_warning(self, password: str) -> None:
        """Sudo timed out (likely fingerprint auth). Proceed with a warning."""
        self.query_one("#password-error", Static).update(
            "[bold yellow]Sudo timed out[/bold yellow] — fingerprint auth may "
            "be interfering.\nProceeding; Ansible will verify the password."
        )
        self.app.push_screen(
            BootstrapRunScreen(self.mode, self.phases, password),
        )


class BootstrapRunScreen(Screen):
    """Executes bootstrap: prereqs, galaxy, ansible-playbook with live output."""

    BINDINGS = [
        ("q", "confirm_quit", "Quit"),
    ]

    def __init__(
        self, mode: str, phases: list[str], become_pass: str
    ) -> None:
        super().__init__()
        self.mode = mode
        self.phases = phases
        self.become_pass = become_pass
        self._finished = False
        self._success = False
        self._log_file = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="run-layout"):
            with Vertical(id="step-sidebar"):
                yield Static("[bold]Steps[/bold]", id="sidebar-title")
                yield Static("", id="step-list")
            with Vertical(id="run-main"):
                yield RichLog(id="output", highlight=True, markup=True, wrap=True)
        with Horizontal(id="run-footer-buttons"):
            yield Button("Done", id="done", variant="primary", disabled=True)
            yield Button("Back to Menu", id="back", disabled=True)
            yield Button("Send Log", id="send-log", disabled=True)
        yield Static(
            "[dim]Tab to move between buttons, Enter to press[/dim]",
            id="run-hint",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._run_bootstrap()

    @work(thread=True)
    def _run_bootstrap(self) -> None:
        """Run the full bootstrap pipeline in a background thread."""
        import re
        from datetime import datetime, timezone

        platform = self.app.platform
        platform_dir = "macos" if platform == "macos" else "linux"
        apply_system_roles = "system" in self.phases

        # Create fresh bootstrap.log for this run.
        self._log_file = open(BOOTSTRAP_LOG, "w")
        self._log_file.write(
            f"Bootstrap started: {datetime.now(timezone.utc).isoformat()}\n"
            f"Mode: {self.mode}  Platform: {platform}\n"
            f"Phases: {', '.join(self.phases)}\n"
            f"{'=' * 60}\n\n"
        )

        steps = [
            ("Install prerequisites", self._step_prereqs),
            ("Install Ansible Galaxy collections", self._step_galaxy),
            ("Resolve age key", self._step_age_key),
            ("Run Ansible playbook", self._step_ansible),
        ]

        self.app.call_from_thread(
            self._update_sidebar, steps, -1
        )

        success = True
        for i, (label, step_fn) in enumerate(steps):
            self.app.call_from_thread(
                self._update_sidebar, steps, i
            )
            self.app.call_from_thread(
                self._log, f"\n[bold cyan]>>> {label}[/bold cyan]\n"
            )
            try:
                step_fn(platform, platform_dir, apply_system_roles)
            except Exception as exc:
                self.app.call_from_thread(
                    self._log,
                    f"\n[bold red]ERROR:[/bold red] {exc}\n"
                )
                logger.exception("Bootstrap step failed: %s", label)
                success = False
                break

        log_path = str(BOOTSTRAP_LOG)
        if success:
            self.app.call_from_thread(
                self._update_sidebar, steps, len(steps)
            )
            self.app.call_from_thread(
                self._log,
                "\n[bold green]Bootstrap complete![/bold green]\n"
                "[dim]Shell configs will reload automatically "
                "when you press Done.[/dim]\n"
                f"[dim]Log: {log_path}[/dim]\n"
            )
        else:
            self.app.call_from_thread(
                self._log,
                "\n[bold red]Bootstrap failed.[/bold red] "
                "Fix the issue above and re-run.\n"
                f"[dim]Log: {log_path}[/dim]\n"
            )

        # Append ansible log if it exists.
        if ANSIBLE_LOG.exists():
            self._log_file.write(f"\n{'=' * 60}\n")
            self._log_file.write("Ansible log (from ~/.local/log/ansible.log):\n")
            self._log_file.write(f"{'=' * 60}\n\n")
            self._log_file.write(ANSIBLE_LOG.read_text())

        self._log_file.close()
        self._log_file = None
        self._finished = True
        self._success = success
        self.app.call_from_thread(self._enable_done_buttons)

    def _step_prereqs(
        self, platform: str, _platform_dir: str, _apply_system: bool
    ) -> None:
        from ..lib.prereqs import install_bootstrap_prereqs

        install_bootstrap_prereqs(
            platform, on_message=lambda msg: self.app.call_from_thread(
                self._log, f"  {msg}"
            )
        )

    def _step_galaxy(
        self, _platform: str, _platform_dir: str, _apply_system: bool
    ) -> None:
        requirements = REPO_ROOT / "shared" / "requirements.yml"
        self._run_streaming(
            ["ansible-galaxy", "collection", "install",
             "-r", str(requirements)],
        )

    def _step_age_key(
        self, _platform: str, _platform_dir: str, _apply_system: bool
    ) -> None:
        from ..lib.age import generate_or_load_age_key

        status_msg, public_key = generate_or_load_age_key(self.app.runner)
        self.app.call_from_thread(self._log, f"  {status_msg}")
        self.app.call_from_thread(
            self._log,
            f"  [dim]Public key: {public_key}[/dim]"
        )

    _SUDOERS_TEMP = "/etc/sudoers.d/99-bootstrap-temp"

    def _step_ansible(
        self, platform: str, platform_dir: str, apply_system_roles: bool
    ) -> None:
        ansible_cfg = REPO_ROOT / platform_dir / "ansible.cfg"
        playbook = REPO_ROOT / platform_dir / "site.yml"

        # Grant temporary NOPASSWD sudo for the bootstrap run.
        # Broken PAM modules (e.g. pam_fingwit on Mint) hang for ~10s on
        # every sudo invocation, which causes Ansible's become prompt
        # detection to time out.  A NOPASSWD sudoers entry lets sudo skip
        # PAM authentication entirely.  The initial `sudo -S` to create
        # the entry goes through PAM once (~10s) but completes within
        # the 30-second timeout.
        self._grant_nopasswd_sudo()
        try:
            cmd = [
                "ansible-playbook", str(playbook),
                "-e", f"workstation_dir={REPO_ROOT}",
                "-e", f"bootstrap_mode={self.mode}",
                "-e", f"apply_system_roles={str(apply_system_roles).lower()}",
                "-e", f"platform={platform}",
                "-e", f"platform_dir={platform_dir}",
            ]

            if platform == "macos":
                apply_defaults = "true" if self.mode != "existing_account" else "false"
                cmd.extend(["-e", f"apply_macos_defaults={apply_defaults}"])

            env_extra = {"ANSIBLE_CONFIG": str(ansible_cfg)}
            self._run_streaming(cmd, env_extra=env_extra)
        finally:
            self._revoke_nopasswd_sudo()

    def _grant_nopasswd_sudo(self) -> None:
        """Create a temporary NOPASSWD sudoers entry for the current user."""
        import getpass

        user = getpass.getuser()
        sudoers_line = f"{user} ALL=(ALL) NOPASSWD: ALL"
        result = subprocess.run(
            [
                "sudo", "-S", "sh", "-c",
                f'echo "{sudoers_line}" > {self._SUDOERS_TEMP}'
                f" && chmod 0440 {self._SUDOERS_TEMP}",
            ],
            input=self.become_pass + "\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            logger.warning("Could not create temp sudoers: %s", result.stderr)

    def _revoke_nopasswd_sudo(self) -> None:
        """Remove the temporary NOPASSWD sudoers entry."""
        subprocess.run(
            ["sudo", "-n", "rm", "-f", self._SUDOERS_TEMP],
            capture_output=True,
            timeout=15,
            check=False,
        )

    def _run_streaming(
        self,
        cmd: list[str],
        *,
        env_extra: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        """Run a command and stream stdout/stderr to the RichLog widget."""
        env = os.environ.copy()
        # Strip virtualenv variables so they don't leak through sudo into
        # PAM modules (pam_fingwit.so does execvp("python3") using PATH,
        # and the venv python lacks system packages like gi).
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        venv = os.environ.get("VIRTUAL_ENV")
        clean_path = os.environ.get("PATH", "")
        if venv:
            clean_path = os.pathsep.join(
                p for p in clean_path.split(os.pathsep)
                if not p.startswith(venv)
            )
        env["PATH"] = f"{Path.home()}/.local/bin:{clean_path}"
        if env_extra:
            env.update(env_extra)

        logger.debug("Streaming: %s", " ".join(cmd))

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=cwd,
        )

        for line in proc.stdout:
            stripped = line.rstrip("\n")
            self.app.call_from_thread(self._log_output, stripped)
            logger.debug(stripped)

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Command failed (exit {proc.returncode}): {' '.join(cmd)}"
            )

    def _log(self, text: str) -> None:
        """Write a Rich-markup line to the RichLog widget and log file."""
        import re

        log_widget = self.query_one("#output", RichLog)
        log_widget.write(text)

        if self._log_file and not self._log_file.closed:
            # Strip Rich markup tags for the plain-text log file.
            plain = re.sub(r"\[/?[^\]]*\]", "", text)
            self._log_file.write(plain + "\n")
            self._log_file.flush()

    def _log_output(self, text: str) -> None:
        """Write subprocess output verbatim (no Rich markup parsing)."""
        from rich.text import Text

        log_widget = self.query_one("#output", RichLog)
        log_widget.write(Text(text))

        if self._log_file and not self._log_file.closed:
            self._log_file.write(text + "\n")
            self._log_file.flush()

    def _update_sidebar(
        self, steps: list[tuple[str, object]], current: int
    ) -> None:
        """Update the step sidebar with progress indicators."""
        lines = []
        for i, (label, _) in enumerate(steps):
            if i < current:
                lines.append(f"[green]  {label}[/green]")
            elif i == current:
                lines.append(f"[bold yellow]  {label}[/bold yellow]")
            else:
                lines.append(f"[dim]  {label}[/dim]")
        sidebar = self.query_one("#step-list", Static)
        sidebar.update("\n".join(lines))

    def _enable_done_buttons(self) -> None:
        self.query_one("#done", Button).disabled = False
        self.query_one("#back", Button).disabled = False
        self.query_one("#send-log", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done":
            self.app.exit(result="reload_shell" if self._success else None)
        elif event.button.id == "back":
            # Pop all bootstrap screens back to welcome.
            from .welcome import WelcomeScreen

            while not isinstance(
                self.app.screen, (BootstrapModeScreen, WelcomeScreen)
            ):
                self.app.pop_screen()
            if isinstance(self.app.screen, BootstrapModeScreen):
                self.app.pop_screen()
            # If no WelcomeScreen in the stack (e.g. --start-screen bootstrap),
            # push a fresh one so the user doesn't land on a blank screen.
            if not isinstance(self.app.screen, WelcomeScreen):
                self.app.push_screen(WelcomeScreen())
        elif event.button.id == "send-log":
            self._send_log()

    @work(thread=True)
    def _send_log(self) -> None:
        """Send bootstrap.log via Magic Wormhole."""
        if not BOOTSTRAP_LOG.exists():
            self.app.call_from_thread(
                self._log,
                "[bold red]No bootstrap.log found.[/bold red]"
            )
            return

        send_btn = self.query_one("#send-log", Button)
        self.app.call_from_thread(setattr, send_btn, "disabled", True)
        self.app.call_from_thread(
            self._log,
            "\n[bold cyan]>>> Sending bootstrap.log via Magic Wormhole...[/bold cyan]\n"
        )

        try:
            self._run_streaming(
                ["uv", "run", "--with", "magic-wormhole",
                 "wormhole", "send", str(BOOTSTRAP_LOG)],
            )
            self.app.call_from_thread(
                self._log,
                "\n[bold green]Log sent successfully.[/bold green]\n"
            )
        except RuntimeError:
            self.app.call_from_thread(
                self._log,
                "\n[bold red]Failed to send log.[/bold red]\n"
            )
        finally:
            self.app.call_from_thread(setattr, send_btn, "disabled", False)

    def action_confirm_quit(self) -> None:
        if self._finished:
            self.app.exit()
