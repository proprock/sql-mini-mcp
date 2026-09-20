from __future__ import annotations

import asyncio
import socket
from typing import Any
from uuid import uuid4

import pytest
from mcp import Client
from mcp_types import TextContent
from mysql_support import LiveMySql, build_config, live_mysql

from sql_mini_mcp.config import AppConfig
from sql_mini_mcp.db.registry import EngineRegistry
from sql_mini_mcp.mcp_server import create_server

pytestmark = pytest.mark.integration

__all__ = ["live_mysql"]


def _error_text(result: Any) -> str:
    assert result.is_error is True
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


def test_live_all_metadata_tools(live_mysql: LiveMySql) -> None:
    async def scenario() -> None:
        async with Client(create_server(live_mysql.config), raise_exceptions=True) as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            assert {
                "list_servers",
                "list_databases",
                "list_tables",
                "get_table_definition",
                "list_stored_procedures",
                "get_stored_procedure",
            } <= tools

            servers = await client.call_tool("list_servers")
            assert {
                (item["name"], item["engine"]) for item in servers.structured_content["servers"]
            } == {(alias, live_mysql.engine) for alias in ("app", "hidden", "denied")}

            databases = await client.call_tool(
                "list_databases", {"server": "app", "name_contains": live_mysql.database.upper()}
            )
            assert databases.structured_content == {"databases": [{"name": live_mysql.database}]}
            everything = await client.call_tool("list_databases", {"server": "app"})
            names = {item["name"] for item in everything.structured_content["databases"]}
            assert names.isdisjoint({"information_schema", "mysql", "performance_schema", "sys"})

            tables = await client.call_tool(
                "list_tables", {"server": "app", "database": live_mysql.database}
            )
            assert {
                (item["schema"], item["name"]) for item in tables.structured_content["tables"]
            } == {(None, "users"), (None, "audit_events")}

            definition = await client.call_tool(
                "get_table_definition",
                {"server": "app", "database": live_mysql.database, "table": "USERS"},
            )
            payload = definition.structured_content
            assert payload["schema"] is None
            columns = {column["name"]: column for column in payload["columns"]}
            assert list(columns) == [
                "tenant_id",
                "id",
                "parent_id",
                "email",
                "amount",
                "created",
            ]
            assert columns["id"]["native_type"].upper().startswith("BIGINT")
            assert columns["id"]["nullable"] is False
            assert columns["email"]["native_type"].upper() == "VARCHAR(120)"
            assert columns["amount"]["native_type"].upper().startswith("DECIMAL(12, 2)")
            assert columns["created"]["native_type"].upper().startswith("DATETIME")
            assert payload["primary_key"]["columns"] == ["tenant_id", "id"]
            assert payload["foreign_keys"][0]["columns"] == ["tenant_id", "parent_id"]
            assert payload["foreign_keys"][0]["referred_table"] == "users"
            assert payload["unique_constraints"][0]["columns"] == ["tenant_id", "email"]
            assert any(index["name"] == "ix_users_email" for index in payload["indexes"])

            procedures = await client.call_tool(
                "list_stored_procedures",
                {"server": "app", "database": live_mysql.database, "name_contains": "PROC"},
            )
            assert {
                (item["schema"], item["name"])
                for item in procedures.structured_content["stored_procedures"]
            } == {(None, "visible_proc"), (None, "other_proc")}
            procedure = await client.call_tool(
                "get_stored_procedure",
                {"server": "app", "database": live_mysql.database, "name": "VISIBLE_PROC"},
            )
            assert procedure.structured_content["schema"] is None
            assert procedure.structured_content["definition_available"] is True
            assert "SELECT 1" in procedure.structured_content["definition"]

    asyncio.run(scenario())


def test_live_safe_error_and_permission_paths(live_mysql: LiveMySql) -> None:
    async def scenario() -> None:
        async with Client(create_server(live_mysql.config), raise_exceptions=True) as client:
            missing = await client.call_tool(
                "get_table_definition",
                {"server": "app", "database": live_mysql.database, "table": "missing_table"},
            )
            assert "NOT_FOUND" in _error_text(missing)

            with_schema = await client.call_tool(
                "get_table_definition",
                {
                    "server": "app",
                    "database": live_mysql.database,
                    "schema": "dbo",
                    "table": "users",
                },
            )
            assert "NOT_FOUND" in _error_text(with_schema)

            hidden = await client.call_tool(
                "get_stored_procedure",
                {"server": "hidden", "database": live_mysql.database, "name": "visible_proc"},
            )
            assert hidden.is_error is False
            assert hidden.structured_content["definition"] is None
            assert hidden.structured_content["definition_available"] is False

            denied = await client.call_tool(
                "list_tables", {"server": "denied", "database": live_mysql.database}
            )
            denied_text = _error_text(denied)
            assert "ACCESS_DENIED" in denied_text
            assert live_mysql.database not in denied_text

            invalid = await client.call_tool(
                "list_tables", {"server": "app", "database": f"missing_{uuid4().hex}"}
            )
            invalid_text = _error_text(invalid)
            assert "ACCESS_DENIED" in invalid_text or "CONNECTION_FAILED" in invalid_text

            sql = await client.call_tool(
                "execute_sql",
                {"server": "app", "database": live_mysql.database, "sql": "SELECT 1"},
            )
            assert "ACCESS_LEVEL_DENIED" in _error_text(sql)

    asyncio.run(scenario())


def test_live_concurrent_calls_do_not_share_connections(live_mysql: LiveMySql) -> None:
    async def scenario() -> None:
        async with Client(create_server(live_mysql.config), raise_exceptions=True) as client:
            results = await asyncio.gather(
                *(
                    client.call_tool(
                        "get_table_definition",
                        {"server": "app", "database": live_mysql.database, "table": "users"},
                    )
                    for _ in range(8)
                )
            )
            assert all(result.is_error is False for result in results)

    asyncio.run(scenario())


def test_live_driver_read_timeout_maps_to_timeout_and_pools_are_disposed(
    live_mysql: LiveMySql, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A listener that accepts connections but never answers exercises the PyMySQL
    # read_timeout wiring end to end; LOCK TABLES does not block the SHOW statements
    # used by reflection, so it cannot provoke a timeout.
    instances: list[EngineRegistry] = []

    class CapturingRegistry(EngineRegistry):
        def __init__(self, config: AppConfig) -> None:
            super().__init__(config)
            instances.append(self)

    monkeypatch.setattr("sql_mini_mcp.mcp_server.EngineRegistry", CapturingRegistry)
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen(5)
        config = build_config(
            live_mysql.engine,
            live_mysql.admin_url.set(host="127.0.0.1", port=silent.getsockname()[1]),
            live_mysql.database,
            {"app": ("nobody", "nothing")},
            timeout=1,
        )

        async def scenario() -> Any:
            async with Client(create_server(config), raise_exceptions=True) as client:
                return await client.call_tool(
                    "list_tables", {"server": "app", "database": live_mysql.database}
                )

        assert "TIMEOUT" in _error_text(asyncio.run(scenario()))

    assert len(instances) == 1
    assert instances[0].cached_engine_count == 0
