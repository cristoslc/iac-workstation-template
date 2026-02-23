"""WelcomeScreen — state detection and main menu."""

from __future__ import annotations

import logging
import subprocess

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from ..lib.runner import REPO_ROOT
from ..lib.state import detect_resume_state

logger = logging.getLogger("setup")


class WelcomeScreen(Screen):
    """Detects repo state and presents appropriate menu options."""

    BINDINGS = [
        ("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-content"):
            yield Static(
                "[bold]Workstation Setup[/bold]\n\n"
                "Detecting current state...",
                id="status",
            )
            yield OptionList(id="menu")
            yield Static("", id="nav-hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#menu", OptionList).display = False
        self._detect_state()

    @work(thread=True)
    def _detect_state(self) -> None:
        """Detect repo state in a background thread."""
        state = detect_resume_state(self.app.runner)
        self.app.call_from_thread(self._show_menu, state)

    def _show_menu(self, state) -> None:
        """Update the screen with detected state and menu options."""
        status = self.query_one("#status", Static)
        menu = self.query_one("#menu", OptionList)
        menu.clear_options()

        if not state.is_personalized:
            # Fresh template — needs first-run.
            status.update(
                "[bold]Workstation Setup[/bold]\n\n"
                "[yellow]This repo has not been personalized yet.[/yellow]\n"
                "The first-run wizard will generate an age key, "
                "collect your GitHub info,\n"
                "and encrypt your secrets."
            )
            menu.add_options([
                Option("Start First-Run Setup", id="first-run"),
                Option("Update and Relaunch", id="update"),
                Option("Quit", id="quit"),
            ])
        else:
            # Personalized — show full menu regardless of pending steps.
            origin_info = ""
            result = self.app.runner.git(
                "remote", "get-url", "origin", check=False
            )
            if result.returncode == 0:
                origin_info = f"\n[dim]Origin: {result.stdout.strip()}[/dim]"

            notes = ""
            if state.pending:
                pending_text = ", ".join(state.pending)
                notes += (
                    f"\n[yellow]Incomplete first-run steps: "
                    f"{pending_text}[/yellow]"
                )
            if state.has_placeholder_secrets:
                notes += (
                    "\n[yellow]Secrets contain placeholders — "
                    "use Edit Secrets to fill them in.[/yellow]"
                )

            status.update(
                "[bold]Workstation Setup[/bold]\n\n"
                f"[green]Repo is personalized.[/green]{origin_info}"
                f"{notes}"
            )
            menu.add_options([
                Option("Bootstrap This Machine", id="bootstrap"),
                Option("Edit Secrets", id="edit-secrets"),
                Option("Re-Run First-Time Setup", id="first-run"),
                Option("Update and Relaunch", id="update"),
                Option("Quit", id="quit"),
            ])

        menu.highlighted = 0
        menu.display = True
        menu.focus()
        self._show_hint()

    def _show_hint(self) -> None:
        self.query_one("#nav-hint", Static).update(
            "[dim]Arrow keys to browse, Enter to select[/dim]"
        )

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Handle menu option selection."""
        option_id = event.option.id
        if option_id == "quit":
            self.app.exit()
        elif option_id == "bootstrap":
            from .bootstrap import BootstrapModeScreen
            self.app.push_screen(BootstrapModeScreen())
        elif option_id == "first-run":
            self.app.push_screen(FirstRunPlaceholderScreen())
        elif option_id == "edit-secrets":
            self.app.push_screen(SecretsPlaceholderScreen())
        elif option_id == "update":
            self._run_update()

    @work(thread=True)
    def _run_update(self) -> None:
        """Pull latest changes and signal the app to relaunch."""
        status = self.query_one("#status", Static)
        menu = self.query_one("#menu", OptionList)
        self.app.call_from_thread(menu.__setattr__, "display", False)
        self.app.call_from_thread(
            status.update,
            "[bold]Workstation Setup[/bold]\n\n"
            "[dim]Pulling latest changes...[/dim]"
        )

        try:
            result = subprocess.run(
                ["git", "pull", "--ff-only"],
                capture_output=True, text=True,
                cwd=str(REPO_ROOT), timeout=30,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                logger.info("git pull: %s", output)
                if "Already up to date" in output:
                    self.app.call_from_thread(
                        status.update,
                        "[bold]Workstation Setup[/bold]\n\n"
                        "[green]Already up to date.[/green] Relaunching..."
                    )
                else:
                    self.app.call_from_thread(
                        status.update,
                        "[bold]Workstation Setup[/bold]\n\n"
                        f"[green]Updated.[/green]\n[dim]{output}[/dim]\n\n"
                        "Relaunching..."
                    )
                # Signal main() to re-exec after Textual exits.
                self.app.exit(result="relaunch")
            else:
                logger.warning("git pull failed: %s", result.stderr.strip())
                self.app.call_from_thread(
                    status.update,
                    "[bold]Workstation Setup[/bold]\n\n"
                    f"[red]Update failed:[/red]\n{result.stderr.strip()}"
                )
                self.app.call_from_thread(menu.__setattr__, "display", True)
        except subprocess.TimeoutExpired:
            logger.warning("git pull timed out")
            self.app.call_from_thread(
                status.update,
                "[bold]Workstation Setup[/bold]\n\n"
                "[red]Update timed out.[/red] Check your network connection."
            )
            self.app.call_from_thread(menu.__setattr__, "display", True)


# Placeholder screens — will be replaced in Phase 3.


class FirstRunPlaceholderScreen(Screen):
    """Temporary placeholder until Phase 3 implements the full first-run flow."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-content"):
            yield Static(
                "[bold]First-Run Setup[/bold]\n\n"
                "The full first-run TUI is coming in Phase 3.\n"
                "For now, exit and run:\n\n"
                "  [cyan]./first-run.sh[/cyan]\n\n"
                "[dim]Tab to reach Back, Enter to press[/dim]"
            )
            yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()


class SecretsPlaceholderScreen(Screen):
    """Temporary placeholder until Phase 3 implements secrets editing."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-content"):
            yield Static(
                "[bold]Edit Secrets[/bold]\n\n"
                "The secrets TUI is coming in Phase 3.\n"
                "For now, exit and run:\n\n"
                "  [cyan]make edit-secrets-shared[/cyan]\n\n"
                "[dim]Tab to reach Back, Enter to press[/dim]"
            )
            yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
