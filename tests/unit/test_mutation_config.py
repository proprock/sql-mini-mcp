from __future__ import annotations

import tomllib
from pathlib import Path


def test_mutmut_copies_the_tools_directory_for_precommit_snapshot_checker() -> None:
    pyproject_file = Path(__file__).parents[2] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_file.read_text(encoding="utf-8"))

    assert "tools" in pyproject["tool"]["mutmut"]["also_copy"]
