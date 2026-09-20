from __future__ import annotations

import pytest

from sql_mini_mcp.errors import DomainError
from sql_mini_mcp.models import TableSummary
from sql_mini_mcp.service import DatabaseService


def test_resolve_table_requires_schema_when_name_is_ambiguous() -> None:
    tables = [
        TableSummary(schema_="dbo", name="Users"),
        TableSummary(schema_="audit", name="Users"),
    ]

    with pytest.raises(DomainError, match="AMBIGUOUS_OBJECT"):
        DatabaseService._resolve_table(tables, "users", None)


def test_resolve_table_matches_case_insensitively() -> None:
    tables = [TableSummary(schema_="dbo", name="Users")]

    selected = DatabaseService._resolve_table(tables, "users", "DBO")

    assert selected.name == "Users"


def test_resolve_table_uses_explicit_schema_for_duplicate_names() -> None:
    tables = [
        TableSummary(schema_="dbo", name="Users"),
        TableSummary(schema_="audit", name="Users"),
    ]

    selected = DatabaseService._resolve_table(tables, "USERS", "Audit")

    assert selected.schema_ == "audit"


def test_resolve_table_returns_not_found_for_missing_name() -> None:
    with pytest.raises(DomainError, match="NOT_FOUND"):
        DatabaseService._resolve_table([], "missing", None)
