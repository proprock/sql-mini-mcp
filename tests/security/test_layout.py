from importlib import import_module

import pytest

SECURITY_MODULES = ("parser", "schema", "policy", "tokens", "validated_query", "executor")


@pytest.mark.parametrize("name", SECURITY_MODULES)
def test_security_module_is_importable(name: str) -> None:
    assert import_module(f"sql_safe_mcp.security.{name}")
