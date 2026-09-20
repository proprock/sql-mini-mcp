from importlib.metadata import version

from sql_mini_mcp import __version__


def test_distribution_and_runtime_versions_match_release() -> None:
    assert __version__ == "0.9.0"
    assert version("sql-mini-mcp") == "0.9.0"
