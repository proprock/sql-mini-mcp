from __future__ import annotations

import asyncio

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
            result = await client.call_tool("list_servers")
            assert result.is_error is False
            assert result.structured_content == {
                "servers": [{"name": "legacy", "engine": "sqlserver", "access_level": "metadata"}]
            }

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
