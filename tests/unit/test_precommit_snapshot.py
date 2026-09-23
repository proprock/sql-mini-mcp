from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

CHECKER = Path(__file__).parents[2] / "tools" / "check_precommit_snapshot.py"
Problems = Callable[[tuple[str, ...], tuple[str, ...], tuple[str, ...]], tuple[str, ...]]


def load_checker() -> dict[str, object]:
    return runpy.run_path(str(CHECKER), run_name="precommit_snapshot_checker")


def load_problems() -> Problems:
    return cast(Problems, load_checker()["problems"])


def test_snapshot_checker_allows_consistent_index() -> None:
    problems = load_problems()

    assert problems((), (), ()) == ()


def test_snapshot_checker_explains_untracked_test_files() -> None:
    problems = load_problems()

    result = problems((), (), ("tests/unit/test_new_behavior.py",))

    assert result == (
        "Untracked code or test files are not part of the staged snapshot:",
        "  - tests/unit/test_new_behavior.py",
        "Stage or remove these files before committing.",
    )


def test_snapshot_checker_explains_staged_tests_with_unstaged_implementation() -> None:
    problems = load_problems()

    result = problems(
        ("tests/unit/test_seed_data_scripts.py",),
        ("scripts/seed-data.ps1",),
        (),
    )

    assert result == (
        "Staged tests may depend on unstaged implementation files:",
        "  staged test: tests/unit/test_seed_data_scripts.py",
        "  unstaged implementation: scripts/seed-data.ps1",
        "Stage related files together, or unstage the tests before committing.",
    )
