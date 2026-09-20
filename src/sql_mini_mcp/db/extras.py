from __future__ import annotations

from typing import Protocol

from sqlalchemy import Connection

from sql_mini_mcp.models import StoredProcedureDefinition, StoredProcedureSummary


class DatabaseExtras(Protocol):
    def list_databases(self, connection: Connection) -> list[str]: ...

    def list_stored_procedures(
        self, connection: Connection, database: str
    ) -> list[StoredProcedureSummary]: ...

    def get_stored_procedure(
        self,
        connection: Connection,
        database: str,
        schema: str | None,
        name: str,
    ) -> StoredProcedureDefinition | None: ...


def extras_for(engine: str) -> DatabaseExtras:
    if engine == "sqlserver":
        from sql_mini_mcp.db.sqlserver import SqlServerExtras

        return SqlServerExtras()
    raise ValueError(f"unsupported engine {engine!r}")
