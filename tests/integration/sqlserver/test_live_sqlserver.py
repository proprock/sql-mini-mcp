from __future__ import annotations

import asyncio
import os
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from mcp import Client
from mcp_types import TextContent
from pydantic import SecretStr
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import URL, make_url

from sql_mini_mcp.config import AppConfig, RuntimeConfig, ServerConfig
from sql_mini_mcp.db.reflection import get_table_definition as reflect_table_definition
from sql_mini_mcp.db.registry import EngineRegistry
from sql_mini_mcp.mcp_server import create_server

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class LiveDatabase:
    admin_url: URL
    config: AppConfig
    database: str
    alpha_schema: str
    beta_schema: str


def _identifier(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ValueError("test identifiers must be alphanumeric with optional underscores")
    return f"[{value}]"


def _url_for(admin_url: URL, login: str, password: str, database: str) -> str:
    return admin_url.set(
        username=login,
        password=password,
        database=database,
    ).render_as_string(hide_password=False)


def _execute_batch(connection: Connection, statements: list[str]) -> None:
    for statement in statements:
        connection.exec_driver_sql(statement)


@pytest.fixture(scope="module")
def live_database() -> Iterator[LiveDatabase]:
    raw_url = os.environ.get("SQL_MINI_MCP_TEST_SQLSERVER_URL")
    if not raw_url:
        pytest.skip("SQL_MINI_MCP_TEST_SQLSERVER_URL is not configured")

    suffix = uuid4().hex[:12]
    database = "SqlMiniMcpTests"
    alpha_schema = f"alpha_{suffix}"
    beta_schema = f"beta_{suffix}"
    app_login = f"smm_app_{suffix}"
    hidden_login = f"smm_hidden_{suffix}"
    denied_login = f"smm_denied_{suffix}"
    app_password = "App!A1" + secrets.token_hex(16)
    hidden_password = "Hidden!A1" + secrets.token_hex(16)
    denied_password = "Denied!A1" + secrets.token_hex(16)
    admin_url = make_url(raw_url).set(database="master")
    admin_engine = create_engine(admin_url, pool_pre_ping=True)

    db = _identifier(database)
    alpha = _identifier(alpha_schema)
    beta = _identifier(beta_schema)
    app = _identifier(app_login)
    hidden = _identifier(hidden_login)
    denied = _identifier(denied_login)

    try:
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            _execute_batch(
                connection,
                [
                    f"IF DB_ID('{database}') IS NULL EXEC(N'CREATE DATABASE {db}')",
                    f"ALTER DATABASE {db} SET COMPATIBILITY_LEVEL = 130",
                    f"CREATE LOGIN {app} WITH PASSWORD = '{app_password}', CHECK_POLICY = OFF",
                    f"CREATE LOGIN {hidden} WITH PASSWORD = '{hidden_password}', "
                    "CHECK_POLICY = OFF",
                    f"CREATE LOGIN {denied} WITH PASSWORD = '{denied_password}', "
                    "CHECK_POLICY = OFF",
                    f"CREATE USER {denied} FOR LOGIN {denied}",
                    f"DENY SELECT ON OBJECT::sys.databases TO {denied}",
                ],
            )

        database_admin = create_engine(admin_url.set(database=database), pool_pre_ping=True)
        try:
            with database_admin.begin() as connection:
                _execute_batch(
                    connection,
                    [
                        f"CREATE SCHEMA {alpha} AUTHORIZATION dbo",
                        f"CREATE SCHEMA {beta} AUTHORIZATION dbo",
                        f"CREATE TABLE {alpha}.[Parents] ("
                        "[TenantId] int NOT NULL, [Id] int NOT NULL, "
                        "CONSTRAINT [PK_Parents] PRIMARY KEY ([TenantId], [Id]))",
                        f"CREATE TABLE {alpha}.[Users] ("
                        "[TenantId] int NOT NULL, [Id] bigint IDENTITY(1,1) NOT NULL, "
                        "[ParentId] int NOT NULL, [Email] nvarchar(100) NOT NULL, "
                        "[Amount] decimal(10,2) NULL CONSTRAINT [DF_Users_Amount] DEFAULT ((0)), "
                        "[DisplayKey] AS (concat([TenantId],'-',[Id])) PERSISTED, "
                        "CONSTRAINT [PK_Users] PRIMARY KEY ([TenantId], [Id]), "
                        "CONSTRAINT [FK_Users_Parents] FOREIGN KEY ([TenantId], [ParentId]) "
                        f"REFERENCES {alpha}.[Parents] ([TenantId], [Id]), "
                        "CONSTRAINT [UQ_Users_Email] UNIQUE ([TenantId], [Email]))",
                        f"CREATE INDEX [IX_Users_Email] ON {alpha}.[Users] ([Email])",
                        f"CREATE TABLE {beta}.[Users] ([Id] int NOT NULL PRIMARY KEY)",
                        f"CREATE PROCEDURE {alpha}.[VisibleProc] AS SELECT 1 AS [Value]",
                        f"CREATE PROCEDURE {alpha}.[HiddenProc] AS SELECT 2 AS [Value]",
                        f"CREATE USER {app} FOR LOGIN {app}",
                        f"CREATE USER {hidden} FOR LOGIN {hidden}",
                        f"GRANT CONNECT TO {app}",
                        f"GRANT SELECT ON SCHEMA::{alpha} TO {app}",
                        f"GRANT SELECT ON SCHEMA::{beta} TO {app}",
                        f"GRANT VIEW DEFINITION TO {app}",
                        f"GRANT CONNECT TO {hidden}",
                        f"GRANT EXECUTE ON OBJECT::{alpha}.[HiddenProc] TO {hidden}",
                    ],
                )
        finally:
            database_admin.dispose()

        config = AppConfig(
            version=1,
            runtime=RuntimeConfig(
                statement_timeout_seconds=2,
                max_concurrent_db_operations=4,
                pool_size=2,
                max_overflow=2,
                engine_cache_size=8,
            ),
            servers={
                "legacy": ServerConfig(
                    engine="sqlserver",
                    connection_url=SecretStr(
                        _url_for(admin_url, app_login, app_password, "master")
                    ),
                ),
                "hidden": ServerConfig(
                    engine="sqlserver",
                    connection_url=SecretStr(
                        _url_for(admin_url, hidden_login, hidden_password, "master")
                    ),
                ),
                "denied": ServerConfig(
                    engine="sqlserver",
                    connection_url=SecretStr(
                        _url_for(admin_url, denied_login, denied_password, "master")
                    ),
                ),
            },
        )
        yield LiveDatabase(admin_url, config, database, alpha_schema, beta_schema)
    finally:
        admin_engine.dispose()
        cleanup_engine = create_engine(admin_url, pool_pre_ping=True)
        database_cleanup_engine = create_engine(
            admin_url.set(database=database), pool_pre_ping=True
        )
        try:
            with cleanup_engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as connection:
                _execute_batch(
                    connection,
                    [
                        "DECLARE @kill nvarchar(max) = N''; "
                        "SELECT @kill += N'KILL ' + CONVERT(nvarchar(11), session_id) + N';' "
                        "FROM sys.dm_exec_sessions WHERE login_name IN "
                        f"(N'{app_login}', N'{hidden_login}', N'{denied_login}'); "
                        "IF @kill <> N'' EXEC sys.sp_executesql @kill",
                    ],
                )
            with database_cleanup_engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as connection:
                _execute_batch(
                    connection,
                    [
                        f"DROP PROCEDURE IF EXISTS {alpha}.[VisibleProc]",
                        f"DROP PROCEDURE IF EXISTS {alpha}.[HiddenProc]",
                        f"DROP TABLE IF EXISTS {beta}.[Users]",
                        f"DROP TABLE IF EXISTS {alpha}.[Users]",
                        f"DROP TABLE IF EXISTS {alpha}.[Parents]",
                        f"IF USER_ID('{app_login}') IS NOT NULL DROP USER {app}",
                        f"IF USER_ID('{hidden_login}') IS NOT NULL DROP USER {hidden}",
                        f"IF SCHEMA_ID('{beta_schema}') IS NOT NULL DROP SCHEMA {beta}",
                        f"IF SCHEMA_ID('{alpha_schema}') IS NOT NULL DROP SCHEMA {alpha}",
                    ],
                )
            with cleanup_engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as connection:
                _execute_batch(
                    connection,
                    [
                        f"IF USER_ID('{denied_login}') IS NOT NULL DROP USER {denied}",
                        "IF EXISTS (SELECT 1 FROM sys.server_principals "
                        f"WHERE name = '{app_login}') "
                        f"DROP LOGIN {app}",
                        "IF EXISTS (SELECT 1 FROM sys.server_principals "
                        f"WHERE name = '{hidden_login}') "
                        f"DROP LOGIN {hidden}",
                        "IF EXISTS (SELECT 1 FROM sys.server_principals "
                        f"WHERE name = '{denied_login}') "
                        f"DROP LOGIN {denied}",
                    ],
                )
        finally:
            database_cleanup_engine.dispose()
            cleanup_engine.dispose()


def test_live_all_six_metadata_tools(live_database: LiveDatabase) -> None:
    reflection_engine = create_engine(
        make_url(live_database.config.servers["legacy"].connection_url.get_secret_value()).set(
            database=live_database.database
        )
    )
    try:
        with reflection_engine.connect() as connection:
            reflected = reflect_table_definition(connection, live_database.alpha_schema, "Users")
        assert [column.name for column in reflected.columns] == [
            "TenantId",
            "Id",
            "ParentId",
            "Email",
            "Amount",
            "DisplayKey",
        ]
    finally:
        reflection_engine.dispose()

    async def scenario() -> None:
        async with Client(create_server(live_database.config), raise_exceptions=True) as client:
            listing = await client.list_tools()
            assert [tool.name for tool in listing.tools] == [
                "list_servers",
                "list_databases",
                "list_tables",
                "get_table_definition",
                "list_stored_procedures",
                "get_stored_procedure",
            ]
            servers = await client.call_tool("list_servers")
            assert servers.is_error is False
            assert {item["name"] for item in servers.structured_content["servers"]} == {
                "legacy",
                "hidden",
                "denied",
            }
            databases = await client.call_tool(
                "list_databases",
                {"server": "legacy", "name_contains": live_database.database.upper()},
            )
            assert databases.structured_content == {"databases": [{"name": live_database.database}]}
            tables = await client.call_tool(
                "list_tables",
                {
                    "server": "legacy",
                    "database": live_database.database,
                    "name_contains": "users",
                },
            )
            assert {
                (item["schema"], item["name"]) for item in tables.structured_content["tables"]
            } == {
                (live_database.alpha_schema, "Users"),
                (live_database.beta_schema, "Users"),
            }
            definition = await client.call_tool(
                "get_table_definition",
                {
                    "server": "legacy",
                    "database": live_database.database,
                    "schema": live_database.alpha_schema,
                    "table": "users",
                },
            )
            payload = definition.structured_content
            assert [column["name"] for column in payload["columns"]] == [
                "TenantId",
                "Id",
                "ParentId",
                "Email",
                "Amount",
                "DisplayKey",
            ]
            assert payload["primary_key"]["columns"] == ["TenantId", "Id"]
            assert payload["foreign_keys"][0]["columns"] == ["TenantId", "ParentId"]
            assert payload["unique_constraints"][0]["columns"] == ["TenantId", "Email"]
            assert any(index["name"] == "IX_Users_Email" for index in payload["indexes"])
            procedures = await client.call_tool(
                "list_stored_procedures",
                {
                    "server": "legacy",
                    "database": live_database.database,
                    "schema": live_database.alpha_schema,
                    "name_contains": "proc",
                },
            )
            assert {
                item["name"] for item in procedures.structured_content["stored_procedures"]
            } == {
                "VisibleProc",
                "HiddenProc",
            }
            procedure = await client.call_tool(
                "get_stored_procedure",
                {
                    "server": "legacy",
                    "database": live_database.database,
                    "schema": live_database.alpha_schema,
                    "name": "visibleproc",
                },
            )
            assert procedure.structured_content["definition_available"] is True
            assert "CREATE PROCEDURE" in procedure.structured_content["definition"].upper()

    asyncio.run(scenario())


def test_live_safe_error_and_permission_paths(live_database: LiveDatabase) -> None:
    async def scenario() -> None:
        async with Client(create_server(live_database.config), raise_exceptions=True) as client:
            ambiguous = await client.call_tool(
                "get_table_definition",
                {"server": "legacy", "database": live_database.database, "table": "USERS"},
            )
            assert ambiguous.is_error is True
            ambiguous_content = ambiguous.content[0]
            assert isinstance(ambiguous_content, TextContent)
            assert "AMBIGUOUS_OBJECT" in ambiguous_content.text
            missing = await client.call_tool(
                "get_table_definition",
                {
                    "server": "legacy",
                    "database": live_database.database,
                    "table": "MissingTable",
                },
            )
            assert missing.is_error is True
            missing_content = missing.content[0]
            assert isinstance(missing_content, TextContent)
            assert "NOT_FOUND" in missing_content.text
            hidden = await client.call_tool(
                "get_stored_procedure",
                {
                    "server": "hidden",
                    "database": live_database.database,
                    "schema": live_database.alpha_schema,
                    "name": "HiddenProc",
                },
            )
            assert hidden.is_error is False
            assert hidden.structured_content["definition"] is None
            assert hidden.structured_content["definition_available"] is False
            denied = await client.call_tool("list_databases", {"server": "denied"})
            assert denied.is_error is True
            denied_content = denied.content[0]
            assert isinstance(denied_content, TextContent)
            assert "ACCESS_DENIED" in denied_content.text
            invalid_database = await client.call_tool(
                "list_tables",
                {"server": "legacy", "database": f"missing_{uuid4().hex}"},
            )
            assert invalid_database.is_error is True
            invalid_content = invalid_database.content[0]
            assert isinstance(invalid_content, TextContent)
            assert "CONNECTION_FAILED" in invalid_content.text

    asyncio.run(scenario())


def test_live_concurrent_calls_do_not_share_connections(live_database: LiveDatabase) -> None:
    async def scenario() -> None:
        async with Client(create_server(live_database.config), raise_exceptions=True) as client:
            results = await asyncio.gather(
                *(
                    client.call_tool(
                        "list_tables",
                        {"server": "legacy", "database": live_database.database},
                    )
                    for _ in range(8)
                )
            )
            assert all(result.is_error is False for result in results)

    asyncio.run(scenario())


def test_live_statement_timeout_and_pool_disposal(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    instances: list[EngineRegistry] = []

    class CapturingRegistry(EngineRegistry):
        def __init__(self, config: AppConfig) -> None:
            super().__init__(config)
            instances.append(self)

    monkeypatch.setattr("sql_mini_mcp.mcp_server.EngineRegistry", CapturingRegistry)
    lock_engine = create_engine(live_database.admin_url.set(database=live_database.database))
    try:
        with lock_engine.connect() as lock_connection:
            transaction = lock_connection.begin()
            try:
                lock_connection.execute(
                    text(
                        f"ALTER TABLE {_identifier(live_database.alpha_schema)}.[Users] "
                        "ADD [TimeoutProbe] int NULL"
                    )
                )

                async def scenario() -> Any:
                    async with Client(
                        create_server(live_database.config), raise_exceptions=True
                    ) as client:
                        return await client.call_tool(
                            "get_table_definition",
                            {
                                "server": "legacy",
                                "database": live_database.database,
                                "schema": live_database.alpha_schema,
                                "table": "Users",
                            },
                        )

                result = asyncio.run(scenario())
                assert result.is_error is True
                content = result.content[0]
                assert isinstance(content, TextContent)
                assert "TIMEOUT" in content.text
            finally:
                transaction.rollback()
    finally:
        lock_engine.dispose()

    assert len(instances) == 1
    assert instances[0].cached_engine_count == 0
