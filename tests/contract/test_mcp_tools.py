from __future__ import annotations

import asyncio
from typing import Any

from mcp import Client
from mcp_types import TextContent
from pydantic import SecretStr

from sql_mini_mcp.config import AppConfig, ServerConfig
from sql_mini_mcp.mcp_server import create_server


def _config() -> AppConfig:
    return AppConfig(
        version=1,
        servers={
            "legacy": ServerConfig(
                engine="sqlserver",
                connection_url=SecretStr("mssql+pyodbc://u:p@sql/master?driver=x"),
            )
        },
    )


def test_metadata_tool_contracts_and_structured_output() -> None:
    async def scenario() -> None:
        async with Client(create_server(_config()), raise_exceptions=True) as client:
            listing = await client.list_tools()
            assert [tool.name for tool in listing.tools] == [
                "list_servers",
                "list_databases",
                "list_tables",
                "get_table_definition",
                "list_stored_procedures",
                "get_stored_procedure",
            ]
            expected_inputs = {
                "list_servers": (set(), set()),
                "list_databases": ({"server", "name_contains"}, {"server"}),
                "list_tables": (
                    {"server", "database", "schema", "name_contains"},
                    {"server", "database"},
                ),
                "get_table_definition": (
                    {"server", "database", "table", "schema"},
                    {"server", "database", "table"},
                ),
                "list_stored_procedures": (
                    {"server", "database", "schema", "name_contains"},
                    {"server", "database"},
                ),
                "get_stored_procedure": (
                    {"server", "database", "name", "schema"},
                    {"server", "database", "name"},
                ),
            }
            for tool in listing.tools:
                properties, required = expected_inputs[tool.name]
                assert set(tool.input_schema.get("properties", {})) == properties
                assert set(tool.input_schema.get("required", [])) == required
                assert tool.annotations is not None
                assert tool.annotations.read_only_hint is True
                assert tool.annotations.open_world_hint is False
            table_list = next(tool for tool in listing.tools if tool.name == "list_tables")
            output_schema = table_list.output_schema
            assert output_schema is not None
            table_item = output_schema["properties"]["tables"]["items"]
            if "$ref" in table_item:
                definition_name = table_item["$ref"].rsplit("/", 1)[-1]
                table_item = output_schema["$defs"][definition_name]
            assert set(table_item["properties"]) == {"schema", "name"}
            assert set(table_item["required"]) == {"schema", "name"}
            result = await client.call_tool("list_servers")
            assert result.is_error is False
            assert result.structured_content == {
                "servers": [{"name": "legacy", "engine": "sqlserver", "access_level": "metadata"}]
            }

    asyncio.run(scenario())


def test_mcp_lifespan_disposes_registry(monkeypatch: Any) -> None:
    instances: list[Any] = []

    class RecordingRegistry:
        def __init__(self, config: AppConfig) -> None:
            self.config = config
            self.disposed = False
            instances.append(self)

        def dispose(self) -> None:
            self.disposed = True

    monkeypatch.setattr("sql_mini_mcp.mcp_server.EngineRegistry", RecordingRegistry)

    async def scenario() -> None:
        async with Client(create_server(_config()), raise_exceptions=True) as client:
            result = await client.call_tool("list_servers")
            assert result.is_error is False
            assert instances[0].disposed is False
        assert instances[0].disposed is True

    asyncio.run(scenario())


def test_domain_error_is_visible_as_tool_error_without_internal_details() -> None:
    async def scenario() -> None:
        async with Client(create_server(_config()), raise_exceptions=True) as client:
            result = await client.call_tool("list_databases", {"server": "missing"})
            assert result.is_error is True
            assert result.structured_content is None
            content = result.content[0]
            assert isinstance(content, TextContent)
            assert "[UNKNOWN_SERVER]" in content.text
            assert "password" not in content.text

    asyncio.run(scenario())
