#!/usr/bin/env python3
"""Workstation setup wizard — unified first-run + bootstrap.

Run via: ./setup.sh
Direct: uv run --with textual,pyyaml scripts/setup.py [--debug]
"""

from __future__ import annotations

import argparse
import os
import sys

# Restrict file creation to owner-only (defense-in-depth).
os.umask(0o077)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Workstation setup wizard (Textual TUI)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--bootstrap", action="store_true",
        help="Skip the welcome menu and go straight to bootstrap",
    )
    args = parser.parse_args()

    from setup_tui.app import SetupApp

    app = SetupApp(debug=args.debug, start_screen="bootstrap" if args.bootstrap else None)
    result = app.run()

    if result == "relaunch":
        # Re-exec through the same entry point after Textual restores the terminal.
        os.execv(sys.executable, [sys.executable] + sys.argv)
    elif result == "reload_shell":
        # Signal setup.sh to exec the user's login shell for config reload.
        sys.exit(7)


if __name__ == "__main__":
    main()
