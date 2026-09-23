from __future__ import annotations

from pathlib import Path


def test_draft_release_identifies_repository_without_a_checkout() -> None:
    workflow = (Path(__file__).parents[2] / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )

    draft_release = workflow.split("  draft_release:\n", maxsplit=1)[1].split(
        "  publish_pypi:\n", maxsplit=1
    )[0]

    assert "GH_REPO: ${{ github.repository }}" in draft_release
