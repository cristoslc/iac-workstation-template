"""ToolRunner — testability seam for all subprocess calls."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("setup")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


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
        private_block = result.stdout.strip()
        return private_block, public_key

    def age_public_key_from_file(self, path: Path) -> str:
        """Extract public key from existing key file."""
        content = path.read_text()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("age1"):
                return stripped
            if "public key:" in stripped.lower():
                return stripped.split(":", 1)[1].strip()
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
