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


def test_release_artifacts_are_uploaded_from_their_preserved_directory() -> None:
    workflow = (Path(__file__).parents[2] / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )

    draft_release = workflow.split("  draft_release:\n", maxsplit=1)[1].split(
        "  publish_pypi:\n", maxsplit=1
    )[0]
    publish_pypi = workflow.split("  publish_pypi:\n", maxsplit=1)[1].split(
        "  publish_registry:\n", maxsplit=1
    )[0]

    assert "path: release-artifacts" in draft_release
    assert 'gh release create "$RELEASE_TAG" --draft --title "$RELEASE_TAG"' in draft_release
    assert 'gh release upload "$RELEASE_TAG" release-artifacts/dist/* --clobber' in draft_release
    assert "path: release-artifacts" in publish_pypi
    assert "packages-dir: release-artifacts/dist/" in publish_pypi
