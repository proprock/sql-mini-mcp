from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
UNSAFE_PASSWORD = "unsafe'password"


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(os.name == "nt", reason="The Bash smoke test runs in POSIX CI.")
def test_bash_seed_script_rejects_an_unsafe_password_before_docker() -> None:
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts" / "seed-data"),
            "--container",
            "missing",
            "--reader-password",
            UNSAFE_PASSWORD,
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "Reader password contains unsupported characters." in result.stderr
    assert UNSAFE_PASSWORD not in result.stderr


@pytest.mark.skipif(
    _powershell() is None, reason="PowerShell is required for this script smoke test."
)
def test_powershell_seed_script_rejects_an_unsafe_password_before_docker() -> None:
    shell = _powershell()
    assert shell is not None
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(ROOT / "scripts" / "seed-data.ps1"),
            "-Container",
            "missing",
            "-ReaderPassword",
            UNSAFE_PASSWORD,
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "Reader password contains unsupported characters." in result.stderr
    assert UNSAFE_PASSWORD not in result.stderr
