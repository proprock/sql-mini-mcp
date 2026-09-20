from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import Connection, inspect

from sql_mini_mcp.models import (
    ColumnDefinition,
    ForeignKeyDefinition,
    IndexDefinition,
    PrimaryKeyDefinition,
    TableDefinition,
    TableSummary,
    UniqueConstraintDefinition,
)

_SQLSERVER_SYSTEM_SCHEMAS = {
    "db_accessadmin",
    "db_backupoperator",
    "db_datareader",
    "db_datawriter",
    "db_ddladmin",
    "db_denydatareader",
    "db_denydatawriter",
    "db_owner",
    "db_securityadmin",
    "guest",
    "information_schema",
    "sys",
}


def list_tables(connection: Connection) -> list[TableSummary]:
    inspector = inspect(connection)
    if getattr(connection.dialect, "name", None) == "mysql":
        # MySQL and MariaDB have no schema level: the connection is bound to one database.
        return [
            TableSummary(schema_=None, name=name) for name in inspector.get_table_names(schema=None)
        ]
    tables: list[TableSummary] = []
    for schema in inspector.get_schema_names():
        if schema.casefold() in _SQLSERVER_SYSTEM_SCHEMAS:
            continue
        tables.extend(
            TableSummary(schema_=schema, name=name)
            for name in inspector.get_table_names(schema=schema)
        )
    return tables


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _normalize_columns(
    connection: Connection, columns: Iterable[Mapping[str, Any]]
) -> list[ColumnDefinition]:
    result: list[ColumnDefinition] = []
    for column in columns:
        type_ = column["type"]
        native_type = str(type_.compile(dialect=connection.dialect))
        result.append(
            ColumnDefinition(
                name=str(column["name"]),
                native_type=native_type,
                nullable=bool(column.get("nullable", True)),
                length=getattr(type_, "length", None),
                precision=getattr(type_, "precision", None),
                scale=getattr(type_, "scale", None),
                autoincrement=column.get("autoincrement"),
                identity=_dict_or_none(column.get("identity")),
                computed=_dict_or_none(column.get("computed")),
                default=None if column.get("default") is None else str(column["default"]),
            )
        )
    return result


def get_table_definition(
    connection: Connection,
    schema: str | None,
    table: str,
) -> TableDefinition:
    inspector = inspect(connection)
    primary_key = inspector.get_pk_constraint(table, schema=schema)
    foreign_keys = inspector.get_foreign_keys(table, schema=schema)
    indexes = inspector.get_indexes(table, schema=schema)
    try:
        unique_constraints = inspector.get_unique_constraints(table, schema=schema)
    except NotImplementedError:
        unique_constraints = [
            {"name": item.get("name"), "column_names": item.get("column_names")}
            for item in indexes
            if item.get("unique")
        ]
    return TableDefinition(
        schema_=schema,
        name=table,
        columns=_normalize_columns(connection, inspector.get_columns(table, schema=schema)),
        primary_key=PrimaryKeyDefinition(
            name=primary_key.get("name"),
            columns=[str(name) for name in primary_key.get("constrained_columns") or []],
        ),
        foreign_keys=[
            ForeignKeyDefinition(
                name=item.get("name"),
                columns=[str(name) for name in item.get("constrained_columns") or []],
                referred_schema=item.get("referred_schema"),
                referred_table=str(item["referred_table"]),
                referred_columns=[str(name) for name in item.get("referred_columns") or []],
                options=dict(item.get("options") or {}),
            )
            for item in foreign_keys
        ],
        unique_constraints=[
            UniqueConstraintDefinition(
                name=None if item.get("name") is None else str(item["name"]),
                columns=[str(name) for name in item.get("column_names") or []],
            )
            for item in unique_constraints
        ],
        indexes=[
            IndexDefinition(
                name=item.get("name"),
                columns=list(item.get("column_names") or []),
                unique=bool(item.get("unique", False)),
                expressions=[str(value) for value in item.get("expressions") or []],
            )
            for item in indexes
        ],
    )
