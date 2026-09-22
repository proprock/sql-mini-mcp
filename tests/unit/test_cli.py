from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path


def _write_config(path: Path, *, extra: str = "") -> Path:
    path.write_text(
        f"""
version: 1
servers:
  legacy:
    engine: sqlserver
    connection_url: mssql+pyodbc://user:password@host/master?driver=x
    {extra}
""",
        encoding="utf-8",
    )
    return path


def _run(
    *arguments: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "sql_safe_mcp", *arguments],
        capture_output=True,
        check=False,
        text=True,
        env=environment,
    )


def test_check_config_returns_zero_for_explicit_path(tmp_path: Path) -> None:
    config = _write_config(tmp_path / "valid.yaml")

    result = _run("--config", str(config), "--check-config")

    assert result.returncode == 0
    assert result.stdout == "Configuration valid: 1 server alias(es).\n"
    assert result.stderr == ""


def test_check_config_uses_environment_path(tmp_path: Path) -> None:
    config = _write_config(tmp_path / "from-environment.yaml")
    environment = os.environ.copy()
    environment["SQL_SAFE_MCP_CONFIG"] = str(config)

    result = _run("--check-config", environment=environment)

    assert result.returncode == 0
    assert "Configuration valid" in result.stdout


def test_gen_pii_key_prints_one_valid_key_without_loading_configuration() -> None:
    result = _run("--gen-pii-key")

    assert result.returncode == 0
    assert result.stderr == ""
    keys = result.stdout.splitlines()
    assert len(keys) == 1
    assert len(base64.b64decode(keys[0], validate=True)) == 32


def test_gen_pii_key_prints_the_requested_number_of_distinct_keys() -> None:
    result = _run("--gen-pii-key", "3")

    assert result.returncode == 0
    assert result.stderr == ""
    keys = result.stdout.splitlines()
    assert len(keys) == 3
    assert len(set(keys)) == 3
    assert all(len(base64.b64decode(key, validate=True)) == 32 for key in keys)


def test_gen_pii_key_rejects_non_positive_count() -> None:
    result = _run("--gen-pii-key", "0")

    assert result.returncode == 2
    assert "positive integer" in result.stderr


def test_invalid_config_returns_two_without_traceback_or_secret(tmp_path: Path) -> None:
    secret = "cli-secret-value"
    config = _write_config(tmp_path / "invalid.yaml", extra=f"unknown: {secret}")

    result = _run("--config", str(config), "--check-config")

    assert result.returncode == 2
    assert "[CONFIG_ERROR]" in result.stderr
    assert "Traceback" not in result.stderr
    assert secret not in result.stderr
    assert "password" not in result.stderr
