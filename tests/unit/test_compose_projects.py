from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("filename", "project_name"),
    [
        ("compose.sqlserver.yml", "sql-safe-mcp-sqlserver"),
        ("compose.mysql.yml", "sql-safe-mcp-mysql"),
    ],
)
def test_live_compose_files_use_stable_project_names(filename: str, project_name: str) -> None:
    compose_file = Path(__file__).parents[2] / filename

    assert compose_file.read_text(encoding="utf-8").startswith(f"name: {project_name}\n")
