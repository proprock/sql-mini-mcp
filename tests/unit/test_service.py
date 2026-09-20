from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import pytest
from pydantic import SecretStr
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from sql_mini_mcp.config import AppConfig, RuntimeConfig, ServerConfig
from sql_mini_mcp.db.registry import EngineRegistry
from sql_mini_mcp.errors import DomainError, ErrorCode
from sql_mini_mcp.models import (
    StoredProcedureDefinition,
    StoredProcedureSummary,
    TableSummary,
)
from sql_mini_mcp.service import DatabaseService


class StubRegistry:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str | None]] = []

    async def run(self, alias: str, database: str | None, operation: object) -> Any:
        del operation
        self.calls.append((alias, database))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _service(*responses: object, max_definition_chars: int = 1024) -> DatabaseService:
    config = AppConfig(
        version=1,
        runtime=RuntimeConfig(max_definition_chars=max_definition_chars),
        servers={
            "zeta": ServerConfig(
                engine="sqlserver",
                connection_url=SecretStr("mssql+pyodbc://u:p@zeta/master?driver=x"),
            ),
            "Alpha": ServerConfig(
                engine="sqlserver",
                connection_url=SecretStr("mssql+pyodbc://u:p@alpha/master?driver=x"),
            ),
        },
    )
    return DatabaseService(config, cast(EngineRegistry, StubRegistry(*responses)))


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


def test_list_servers_and_metadata_filters_are_case_insensitive() -> None:
    service = _service(
        ["master", "Warehouse", "Archive"],
        [
            TableSummary(schema_="dbo", name="Users"),
            TableSummary(schema_="audit", name="UserEvents"),
            TableSummary(schema_="dbo", name="Orders"),
        ],
        [
            StoredProcedureSummary(schema_="dbo", name="RefreshUsers"),
            StoredProcedureSummary(schema_="audit", name="WriteUserEvent"),
            StoredProcedureSummary(schema_="dbo", name="RefreshOrders"),
        ],
    )

    async def scenario() -> None:
        assert [item.name for item in service.list_servers().servers] == ["Alpha", "zeta"]
        databases = await service.list_databases("Alpha", "WARE")
        assert [item.name for item in databases.databases] == ["Warehouse"]
        tables = await service.list_tables("Alpha", "Application", "AUDIT", "user")
        assert [(item.schema_, item.name) for item in tables.tables] == [("audit", "UserEvents")]
        procedures = await service.list_stored_procedures("Alpha", "Application", "dbo", "refresh")
        assert [(item.schema_, item.name) for item in procedures.stored_procedures] == [
            ("dbo", "RefreshOrders"),
            ("dbo", "RefreshUsers"),
        ]

    asyncio.run(scenario())


def test_get_stored_procedure_handles_ambiguity_hidden_and_oversized_definition() -> None:
    ambiguous = _service(
        [
            StoredProcedureSummary(schema_="dbo", name="Refresh"),
            StoredProcedureSummary(schema_="audit", name="Refresh"),
        ]
    )
    hidden = StoredProcedureDefinition(
        schema_="dbo", name="Hidden", definition=None, definition_available=False
    )
    hidden_service = _service(
        [StoredProcedureSummary(schema_="dbo", name="Hidden")],
        hidden,
    )
    oversized_service = _service(
        [StoredProcedureSummary(schema_="dbo", name="Large")],
        StoredProcedureDefinition(
            schema_="dbo", name="Large", definition="x" * 1025, definition_available=True
        ),
    )

    async def scenario() -> None:
        with pytest.raises(DomainError, match="AMBIGUOUS_OBJECT"):
            await ambiguous.get_stored_procedure("Alpha", "Application", "refresh")
        assert (
            await hidden_service.get_stored_procedure(
                "Alpha", "Application", "hidden", schema="DBO"
            )
        ) is hidden
        with pytest.raises(DomainError) as raised:
            await oversized_service.get_stored_procedure("Alpha", "Application", "large", "dbo")
        assert raised.value.code is ErrorCode.DEFINITION_TOO_LARGE

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (
            OperationalError(
                "SELECT secret", {"password": "hidden"}, Exception("HYT00 query timeout")
            ),
            ErrorCode.TIMEOUT,
        ),
        (SqlAlchemyTimeoutError("pool timeout with secret"), ErrorCode.TIMEOUT),
        (
            DBAPIError(
                "SELECT secret", {"password": "hidden"}, Exception("42000 permission denied")
            ),
            ErrorCode.ACCESS_DENIED,
        ),
        (
            OperationalError(
                "SELECT secret", {"password": "hidden"}, Exception("08001 connection failed")
            ),
            ErrorCode.CONNECTION_FAILED,
        ),
        (
            ProgrammingError(
                "SELECT secret",
                {"password": "hidden"},
                Exception("42000 Cannot open database requested by the login. (4060)"),
            ),
            ErrorCode.CONNECTION_FAILED,
        ),
    ],
)
def test_database_failures_map_to_stable_public_codes(
    failure: BaseException, expected: ErrorCode
) -> None:
    service = _service(failure)

    async def scenario() -> None:
        with pytest.raises(DomainError) as raised:
            await service.list_databases("Alpha")
        assert raised.value.code is expected
        public = str(raised.value)
        assert "SELECT secret" not in public
        assert "password" not in public

    asyncio.run(scenario())


def test_unexpected_failure_logs_only_generic_context_and_correlation_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service(RuntimeError("SELECT secret password=hidden"))

    async def scenario() -> None:
        with pytest.raises(DomainError) as raised:
            await service.list_databases("Alpha")
        assert raised.value.code is ErrorCode.DATABASE_ERROR
        assert raised.value.correlation_id is not None

    with caplog.at_level(logging.ERROR, logger="sql_mini_mcp.service"):
        asyncio.run(scenario())

    captured = caplog.text
    assert "Unexpected database operation failure" in captured
    assert "SELECT secret" not in captured
    assert "password" not in captured
