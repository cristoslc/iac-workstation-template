"""SOPS encryption operations."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from .runner import REPO_ROOT, ToolRunner

logger = logging.getLogger("setup")


class EncryptionError(Exception):
    """SOPS encryption or decryption failure."""


def encrypt_secret_files(runner: ToolRunner) -> tuple[int, list[str]]:
    """Find and encrypt all plaintext SOPS files.

    Returns (count_encrypted, status_messages).
    """
    messages = []
    encrypted_count = 0
    patterns = ["**/*.sops.yml", "**/*.sops.yaml", "**/*.sops"]

    for pattern in patterns:
        for sops_file in REPO_ROOT.glob(pattern):
            if "/secrets/" not in str(sops_file):
                continue
            if "/.decrypted/" in str(sops_file):
                continue
            content = sops_file.read_text()
            if '"sops":' in content or "\nsops:" in content or content.startswith("sops:"):
                messages.append(f"Already encrypted: {sops_file.relative_to(REPO_ROOT)}")
                continue

            messages.append(f"Encrypting: {sops_file.relative_to(REPO_ROOT)}")
            runner.sops_encrypt_in_place(sops_file)
            encrypted_count += 1

    messages.append(f"Encrypted {encrypted_count} file(s).")
    return encrypted_count, messages


def write_and_encrypt(
    runner: ToolRunner, target: Path, content: str
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
        logger.info("Encrypted %s", target.name)
    except Exception:
        Path(tmppath).unlink(missing_ok=True)
        raise EncryptionError(f"Failed to encrypt {target.name}")
