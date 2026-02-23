"""Age key generation and resolution."""

from __future__ import annotations

import logging
from pathlib import Path

from .runner import ToolRunner
from .state import AGE_KEY_PATH

logger = logging.getLogger("setup")


class AgeKeyError(Exception):
    """Age key generation or extraction failure."""


def generate_or_load_age_key(runner: ToolRunner) -> tuple[str, str]:
    """Generate age keypair or load existing.

    Returns (status_message, public_key).
    """
    if AGE_KEY_PATH.exists():
        public_key = runner.age_public_key_from_file(AGE_KEY_PATH)
        if not public_key:
            raise AgeKeyError(f"Could not extract public key from {AGE_KEY_PATH}")
        return f"Age key already exists at {AGE_KEY_PATH}", public_key

    logger.info("Generating age keypair...")
    key_dir = AGE_KEY_PATH.parent
    key_dir.mkdir(parents=True, exist_ok=True)

    private_block, public_key = runner.age_keygen()
    if not public_key:
        raise AgeKeyError("age-keygen did not produce a public key")

    AGE_KEY_PATH.write_text(private_block + "\n")
    key_dir.chmod(0o700)
    AGE_KEY_PATH.chmod(0o600)

    return "Age keypair generated.", public_key
