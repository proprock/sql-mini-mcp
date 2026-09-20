"""One MCP server over SQL Server, MySQL, and MariaDB at once (the release matrix).

Needs all three test servers, so it is run by scripts/test-matrix.ps1 and never by the
single-engine gates.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from live_support import LiveDatabase, live_database
from mcp import Client
from mcp_types import TextContent
from mysql_support import LiveMySql, live_mariadb_only, live_mysql_only

from sql_mini_mcp.config import AppConfig, RuntimeConfig
from sql_mini_mcp.mcp_server import create_server
from sql_mini_mcp.security.tokens import TokenCodec

pytestmark = pytest.mark.integration

__all__ = ["live_database", "live_mariadb_only", "live_mysql_only"]


@dataclass(frozen=True)
class EngineCase:
    engine: str
    meta: str  # metadata alias
    secure: str  # pii_safe alias
    key: bytes
    database: str  # metadata database
    sql_database: str
    table: str  # metadata table name
    schema: str | None
    query: str  # execute_sql text with {token}
    email: str


def _cases(mssql: LiveDatabase, mysql: LiveMySql, maria: LiveMySql) -> list[EngineCase]:
    cases = [
        EngineCase(
            "sqlserver",
            "mssql_meta",
            "mssql",
            mssql.pii_key,
            mssql.database,
            mssql.database,
            "Users",
            mssql.alpha_schema,
            f"SELECT Id FROM [{mssql.alpha_schema}].[Users] WHERE Email = '{{token}}'",
            mssql.emails[0],
        )
    ]
    for prefix, live in (("mysql", mysql), ("maria", maria)):
        cases.append(
            EngineCase(
                live.engine,
                f"{prefix}_meta",
                prefix,
                live.key,
                live.database,
                live.sql_database,
                "users",
                None,
                "SELECT id FROM people WHERE email = '{token}'",
                "a@example.com",
            )
        )
    return cases


def _combined(mssql: LiveDatabase, mysql: LiveMySql, maria: LiveMySql) -> AppConfig:
    servers = {
        "mssql_meta": mssql.config.servers["legacy"],
        "mssql": mssql.config.servers["secure"],
        "mysql_meta": mysql.config.servers["app"],
        "mysql": mysql.sql_config.servers["secure"],
        "maria_meta": maria.config.servers["app"],
        "maria": maria.sql_config.servers["secure"],
    }
    return AppConfig(
        version=1, runtime=RuntimeConfig(statement_timeout_seconds=10), servers=servers
    )


def _text(result: Any) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


# Engine-specific free-form details: their presence differs per engine, their keys are not contract.
_OPAQUE = {"options", "identity", "computed"}


def _keys(value: Any) -> Any:
    """The contract shape of a response: field names and list element shapes, never values."""
    if isinstance(value, dict):
        return {key: "opaque" if key in _OPAQUE else _keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return sorted({repr(_keys(item)) for item in value})
    return "value"


def test_same_public_contract_and_token_isolation_on_three_engines(
    live_database: LiveDatabase,
    live_mysql_only: LiveMySql,
    live_mariadb_only: LiveMySql,
) -> None:
    cases = _cases(live_database, live_mysql_only, live_mariadb_only)
    config = _combined(live_database, live_mysql_only, live_mariadb_only)

    async def scenario() -> None:
        async with Client(create_server(config), raise_exceptions=True) as client:
            servers = await client.call_tool("list_servers")
            engines = {
                item["name"]: item["engine"] for item in servers.structured_content["servers"]
            }
            assert {case.secure: case.engine for case in cases} | {
                case.meta: case.engine for case in cases
            } == engines

            shapes: dict[str, list[Any]] = {
                "list_databases": [],
                "list_tables": [],
                "get_table_definition": [],
                "list_stored_procedures": [],
                "execute_sql": [],
            }
            for case in cases:
                databases = await client.call_tool("list_databases", {"server": case.meta})
                shapes["list_databases"].append(_keys(databases.structured_content))
                assert any(
                    item["name"] == case.database
                    for item in databases.structured_content["databases"]
                )

                tables = await client.call_tool(
                    "list_tables", {"server": case.meta, "database": case.database}
                )
                shapes["list_tables"].append(_keys(tables.structured_content))
                assert case.table.casefold() in {
                    item["name"].casefold() for item in tables.structured_content["tables"]
                }

                arguments: dict[str, Any] = {
                    "server": case.meta,
                    "database": case.database,
                    "table": case.table,
                }
                if case.schema is not None:
                    arguments["schema"] = case.schema
                definition = await client.call_tool("get_table_definition", arguments)
                shapes["get_table_definition"].append(_keys(definition.structured_content))
                payload = definition.structured_content
                assert (payload["schema"] is None) == (case.schema is None)
                assert payload["primary_key"]["columns"]

                procedures = await client.call_tool(
                    "list_stored_procedures", {"server": case.meta, "database": case.database}
                )
                shapes["list_stored_procedures"].append(_keys(procedures.structured_content))

                own = TokenCodec(case.secure, case.key).encrypt(case.email)
                result = await client.call_tool(
                    "execute_sql",
                    {
                        "server": case.secure,
                        "database": case.sql_database,
                        "sql": case.query.format(token=own),
                    },
                )
                assert result.is_error is False, _text(result)
                assert result.structured_content["rows"], case.engine
                shapes["execute_sql"].append(_keys(result.structured_content))

            for tool, tool_shapes in shapes.items():
                assert all(shape == tool_shapes[0] for shape in tool_shapes), tool

            failures = set()
            for target in cases:
                for source in cases:
                    if source is target:
                        continue
                    tokens = (
                        TokenCodec(source.secure, source.key).encrypt(source.email),
                        TokenCodec(source.secure, target.key).encrypt(source.email),
                        "pii:v1:AAAA",
                    )
                    for token in tokens:
                        bad = await client.call_tool(
                            "execute_sql",
                            {
                                "server": target.secure,
                                "database": target.sql_database,
                                "sql": target.query.format(token=token),
                            },
                        )
                        assert bad.is_error is True
                        assert "INVALID_PII_TOKEN" in _text(bad)
                        failures.add(_text(bad))
            assert len(failures) == 1, failures

    asyncio.run(scenario())
