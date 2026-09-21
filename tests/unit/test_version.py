import json
from importlib.metadata import version
from pathlib import Path

from sql_safe_mcp import __version__


def test_distribution_and_runtime_versions_match_release() -> None:
    assert __version__ == "1.3.1"
    assert version("sql-safe-mcp") == "1.3.1"


def test_mcp_registry_metadata_matches_the_distribution() -> None:
    project_root = Path(__file__).parents[2]
    metadata = json.loads((project_root / "server.json").read_text(encoding="utf-8"))

    assert metadata["name"] == "io.github.proprock/sql-safe-mcp"
    assert metadata["version"] == __version__
    assert metadata["packages"] == [
        {
            "registryType": "pypi",
            "identifier": "sql-safe-mcp",
            "version": __version__,
            "transport": {"type": "stdio"},
        }
    ]
    assert "<!-- mcp-name: io.github.proprock/sql-safe-mcp -->" in (
        project_root / "README.md"
    ).read_text(encoding="utf-8")
