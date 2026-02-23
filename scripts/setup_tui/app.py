"""SetupApp — the main Textual application."""

from __future__ import annotations

import os
import sys

from textual.app import App

from .lib.runner import ToolRunner
from .lib.setup_logging import setup_logging
from .lib.state import AGE_KEY_PATH
from .screens.welcome import WelcomeScreen

APP_CSS = """\
Screen {
    background: $surface;
}

#main-content {
    width: 1fr;
    height: 1fr;
    padding: 1 2;
}

.step-complete {
    color: $success;
}

.step-current {
    color: $warning;
    text-style: bold;
}

.step-pending {
    color: $text-muted;
}

.sidebar {
    width: 24;
    padding: 1 2;
    border-right: solid $primary-background;
}

.status-ok {
    color: $success;
}

.status-warn {
    color: $warning;
}

.status-error {
    color: $error;
}

#menu {
    width: 50;
    height: auto;
    max-height: 12;
    margin: 1 0;
}

#run-layout {
    width: 1fr;
    height: 1fr;
}

#step-sidebar {
    width: 36;
    padding: 1 2;
    border-right: solid $primary-background;
}

#run-main {
    width: 1fr;
    height: 1fr;
    padding: 1 2;
}

#output {
    width: 1fr;
    height: 1fr;
}

#run-footer-buttons {
    height: auto;
    padding: 0 2;
    align-horizontal: center;
}

#run-footer-buttons Button {
    margin: 0 1;
}

#phase-checkboxes {
    height: auto;
    padding: 0 0 1 0;
}

#sudo-password {
    width: 40;
    margin: 1 0;
}

#password-error {
    height: auto;
    margin: 0 0 1 0;
}
"""


class SetupApp(App):
    """Workstation setup wizard — unified first-run + bootstrap."""

    CSS = APP_CSS
    TITLE = "Workstation Setup"

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self, *, debug: bool = False, start_screen: str | None = None
    ) -> None:
        super().__init__()
        self._debug_mode = debug
        self._start_screen = start_screen
        self.runner = ToolRunner(debug=debug)
        self.platform = os.environ.get("PLATFORM") or (
            "macos" if sys.platform == "darwin" else "linux"
        )
        # SOPS age key file.
        os.environ["SOPS_AGE_KEY_FILE"] = str(AGE_KEY_PATH)

    def on_mount(self) -> None:
        setup_logging(debug=self._debug_mode)
        if self._start_screen == "bootstrap":
            from .screens.bootstrap import BootstrapModeScreen

            self.push_screen(BootstrapModeScreen())
        else:
            self.push_screen(WelcomeScreen())
