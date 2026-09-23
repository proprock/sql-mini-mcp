"""Explain index/worktree combinations that make commit-time tests misleading."""

from __future__ import annotations

import subprocess
import sys


def _git_paths(*arguments: str) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(path for path in result.stdout.splitlines() if path)


def problems(
    staged_tests: tuple[str, ...],
    unstaged_implementation: tuple[str, ...],
    untracked_files: tuple[str, ...],
) -> tuple[str, ...]:
    """Return actionable diagnostics for a potentially inconsistent commit snapshot."""
    messages: list[str] = []
    if untracked_files:
        messages.extend(
            (
                "Untracked code or test files are not part of the staged snapshot:",
                *(f"  - {path}" for path in untracked_files),
                "Stage or remove these files before committing.",
            )
        )
    if staged_tests and unstaged_implementation:
        if messages:
            messages.append("")
        messages.append("Staged tests may depend on unstaged implementation files:")
        messages.extend(f"  staged test: {path}" for path in staged_tests)
        messages.extend(f"  unstaged implementation: {path}" for path in unstaged_implementation)
        messages.append("Stage related files together, or unstage the tests before committing.")
    return tuple(messages)


def main() -> int:
    try:
        messages = problems(
            _git_paths("diff", "--cached", "--name-only", "--", "tests"),
            _git_paths("diff", "--name-only", "--", "src", "scripts"),
            _git_paths(
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                "tests",
                "src",
                "scripts",
            ),
        )
    except subprocess.CalledProcessError:
        print("index-consistency: unable to inspect Git state.", file=sys.stderr)
        return 1

    if not messages:
        return 0

    print("index-consistency: pre-commit tests the staged snapshot.", file=sys.stderr)
    print(*messages, sep="\n", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
