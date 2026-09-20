from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy import Connection

from sql_mini_mcp.db.reflection import get_table_definition, list_tables


class FakeType:
    def __init__(
        self,
        native: str,
        *,
        length: int | None = None,
        precision: int | None = None,
        scale: int | None = None,
    ) -> None:
        self.native = native
        self.length = length
        self.precision = precision
        self.scale = scale

    def compile(self, dialect: object) -> str:
        del dialect
        return self.native


class FakeInspector:
    def __init__(self) -> None:
        self.requested_schemas: list[str | None] = []

    def get_schema_names(self) -> list[str]:
        return [
            "sys",
            "INFORMATION_SCHEMA",
            "guest",
            "db_owner",
            "db_accessadmin",
            "db_securityadmin",
            "db_ddladmin",
            "db_backupoperator",
            "db_datareader",
            "db_datawriter",
            "db_denydatareader",
            "db_denydatawriter",
            "dbo",
            "audit",
        ]

    def get_table_names(self, schema: str | None = None) -> list[str]:
        self.requested_schemas.append(schema)
        return {"dbo": ["Users"], "audit": ["Users", "Events"]}.get(schema or "", [])

    def get_columns(self, table: str, schema: str | None = None) -> list[dict[str, Any]]:
        assert (schema, table) == ("dbo", "Orders")
        return [
            {
                "name": "TenantId",
                "type": FakeType("int", precision=10, scale=0),
                "nullable": False,
                "autoincrement": False,
                "default": "((1))",
            },
            {
                "name": "Id",
                "type": FakeType("bigint", precision=19, scale=0),
                "nullable": False,
                "autoincrement": True,
                "identity": {"start": 1, "increment": 1},
            },
            {
                "name": "DisplayName",
                "type": FakeType("nvarchar(80)", length=80),
                "nullable": True,
                "computed": {"sqltext": "([FirstName]+[LastName])", "persisted": True},
            },
        ]

    def get_pk_constraint(self, table: str, schema: str | None = None) -> dict[str, Any]:
        assert (schema, table) == ("dbo", "Orders")
        return {"name": "PK_Orders", "constrained_columns": ["TenantId", "Id"]}

    def get_foreign_keys(self, table: str, schema: str | None = None) -> list[dict[str, Any]]:
        assert (schema, table) == ("dbo", "Orders")
        return [
            {
                "name": "FK_Orders_Users",
                "constrained_columns": ["TenantId", "UserId"],
                "referred_schema": "dbo",
                "referred_table": "Users",
                "referred_columns": ["TenantId", "Id"],
                "options": {"ondelete": "CASCADE"},
            }
        ]

    def get_unique_constraints(self, table: str, schema: str | None = None) -> list[dict[str, Any]]:
        assert (schema, table) == ("dbo", "Orders")
        return [{"name": "UQ_Orders_Code", "column_names": ["TenantId", "Code"]}]

    def get_indexes(self, table: str, schema: str | None = None) -> list[dict[str, Any]]:
        assert (schema, table) == ("dbo", "Orders")
        return [
            {
                "name": "IX_Orders_Name",
                "column_names": ["DisplayName"],
                "unique": False,
                "expressions": ["lower([DisplayName])"],
            }
        ]


@pytest.fixture
def fake_connection() -> Connection:
    class Value:
        dialect = object()

    return cast(Connection, Value())


def test_list_tables_excludes_all_sqlserver_system_schemas(
    monkeypatch: pytest.MonkeyPatch, fake_connection: Connection
) -> None:
    inspector = FakeInspector()
    monkeypatch.setattr("sql_mini_mcp.db.reflection.inspect", lambda _connection: inspector)

    tables = list_tables(fake_connection)

    assert [(table.schema_, table.name) for table in tables] == [
        ("dbo", "Users"),
        ("audit", "Users"),
        ("audit", "Events"),
    ]
    assert inspector.requested_schemas == ["dbo", "audit"]


class MySqlInspector:
    def __init__(self) -> None:
        self.requested_schemas: list[str | None] = []

    def get_schema_names(self) -> list[str]:
        raise AssertionError("mysql lists only the connected database")

    def get_table_names(self, schema: str | None = None) -> list[str]:
        self.requested_schemas.append(schema)
        return ["orders", "users"]


def test_list_tables_for_mysql_uses_connected_database_and_null_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Value:
        dialect = type("Dialect", (), {"name": "mysql"})()

    inspector = MySqlInspector()
    monkeypatch.setattr("sql_mini_mcp.db.reflection.inspect", lambda _connection: inspector)

    tables = list_tables(cast(Connection, Value()))

    assert [(table.schema_, table.name) for table in tables] == [
        (None, "orders"),
        (None, "users"),
    ]
    assert inspector.requested_schemas == [None]


def test_get_table_definition_normalizes_complete_inspector_payload(
    monkeypatch: pytest.MonkeyPatch, fake_connection: Connection
) -> None:
    monkeypatch.setattr("sql_mini_mcp.db.reflection.inspect", lambda _connection: FakeInspector())

    definition = get_table_definition(fake_connection, "dbo", "Orders")
    payload = definition.model_dump(mode="json", by_alias=True)

    assert payload["columns"] == [
        {
            "name": "TenantId",
            "native_type": "int",
            "nullable": False,
            "length": None,
            "precision": 10,
            "scale": 0,
            "autoincrement": False,
            "identity": None,
            "computed": None,
            "default": "((1))",
        },
        {
            "name": "Id",
            "native_type": "bigint",
            "nullable": False,
            "length": None,
            "precision": 19,
            "scale": 0,
            "autoincrement": True,
            "identity": {"start": 1, "increment": 1},
            "computed": None,
            "default": None,
        },
        {
            "name": "DisplayName",
            "native_type": "nvarchar(80)",
            "nullable": True,
            "length": 80,
            "precision": None,
            "scale": None,
            "autoincrement": None,
            "identity": None,
            "computed": {"sqltext": "([FirstName]+[LastName])", "persisted": True},
            "default": None,
        },
    ]
    assert payload["primary_key"] == {
        "name": "PK_Orders",
        "columns": ["TenantId", "Id"],
    }
    assert payload["foreign_keys"][0]["columns"] == ["TenantId", "UserId"]
    assert payload["foreign_keys"][0]["referred_columns"] == ["TenantId", "Id"]
    assert payload["unique_constraints"][0]["columns"] == ["TenantId", "Code"]
    assert payload["indexes"][0] == {
        "name": "IX_Orders_Name",
        "columns": ["DisplayName"],
        "unique": False,
        "expressions": ["lower([DisplayName])"],
    }


def test_get_table_definition_derives_unique_constraints_when_dialect_omits_api(
    monkeypatch: pytest.MonkeyPatch, fake_connection: Connection
) -> None:
    class SqlServerInspector(FakeInspector):
        def get_unique_constraints(
            self, table: str, schema: str | None = None
        ) -> list[dict[str, Any]]:
            assert (schema, table) == ("dbo", "Orders")
            raise NotImplementedError

        def get_indexes(self, table: str, schema: str | None = None) -> list[dict[str, Any]]:
            assert (schema, table) == ("dbo", "Orders")
            return [
                {
                    "name": "UQ_Orders_Code",
                    "column_names": ["TenantId", "Code"],
                    "unique": True,
                },
                {
                    "name": "IX_Orders_Name",
                    "column_names": ["DisplayName"],
                    "unique": False,
                },
            ]

    monkeypatch.setattr(
        "sql_mini_mcp.db.reflection.inspect", lambda _connection: SqlServerInspector()
    )

    definition = get_table_definition(fake_connection, "dbo", "Orders")

    assert [item.model_dump() for item in definition.unique_constraints] == [
        {"name": "UQ_Orders_Code", "columns": ["TenantId", "Code"]}
    ]
