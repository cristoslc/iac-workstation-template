"""Logging configuration for the setup wizard."""

from __future__ import annotations

import logging
import platform
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / ".local" / "log"
LOG_FILE = LOG_DIR / "setup.log"


def setup_logging(*, debug: bool = False) -> None:
    """Configure dual logging: file (always DEBUG) + console (only in debug mode).

    Console output is handled by Textual widgets, not the logging module.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("setup")
    root_logger.setLevel(logging.DEBUG)

    # File handler -- always captures everything.
    fh = logging.FileHandler(str(LOG_FILE), mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s")
    )
    root_logger.addHandler(fh)

    # Console handler -- only for debug mode (Textual handles normal output).
    if debug:
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(logging.Formatter("[DEBUG] %(message)s"))
        root_logger.addHandler(ch)

    # Log header.
    root_logger.info(
        "setup.py -- %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
    )
    root_logger.info("platform: %s %s", platform.system(), platform.machine())
    root_logger.info("python: %s", sys.version.split()[0])
    root_logger.info("debug: %s", debug)
