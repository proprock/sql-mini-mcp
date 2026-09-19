from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import Connection

from sql_mini_mcp.models import StoredProcedureDefinition, StoredProcedureSummary


class DatabaseExtras(ABC):
    @abstractmethod
    def list_databases(self, connection: Connection) -> list[str]: ...

    @abstractmethod
    def list_stored_procedures(
        self, connection: Connection, database: str
    ) -> list[StoredProcedureSummary]: ...

    @abstractmethod
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
    if engine == "mysql":
        from sql_mini_mcp.db.mysql import MySqlExtras

        return MySqlExtras()
    raise ValueError(f"unsupported engine {engine!r}")
