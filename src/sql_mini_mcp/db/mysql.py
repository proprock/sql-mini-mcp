from __future__ import annotations

from sqlalchemy import Connection, text

from sql_mini_mcp.db.extras import DatabaseExtras
from sql_mini_mcp.models import StoredProcedureDefinition, StoredProcedureSummary


class MySqlExtras(DatabaseExtras):
    def list_databases(self, connection: Connection) -> list[str]:
        return [str(row[0]) for row in connection.execute(text("SHOW DATABASES"))]

    def list_stored_procedures(
        self, connection: Connection, database: str
    ) -> list[StoredProcedureSummary]:
        rows = connection.execute(
            text(
                "SELECT ROUTINE_SCHEMA, ROUTINE_NAME FROM information_schema.routines "
                "WHERE ROUTINE_TYPE = 'PROCEDURE' AND ROUTINE_SCHEMA = :database "
                "ORDER BY ROUTINE_NAME"
            ),
            {"database": database},
        )
        return [StoredProcedureSummary(schema_=None, name=str(row.ROUTINE_NAME)) for row in rows]

    def get_stored_procedure(
        self,
        connection: Connection,
        database: str,
        schema: str | None,
        name: str,
    ) -> StoredProcedureDefinition | None:
        if schema is not None:
            return None
        exists = connection.execute(
            text(
                "SELECT ROUTINE_NAME FROM information_schema.routines "
                "WHERE ROUTINE_TYPE = 'PROCEDURE' AND ROUTINE_SCHEMA = :database "
                "AND ROUTINE_NAME = :name"
            ),
            {"database": database, "name": name},
        ).first()
        if exists is None:
            return None
        preparer = connection.dialect.identifier_preparer
        qualified = f"{preparer.quote(database)}.{preparer.quote(name)}"
        row = connection.exec_driver_sql(f"SHOW CREATE PROCEDURE {qualified}").first()
        if row is None:
            return None
        mapping = row._mapping
        definition = next(
            (value for key, value in mapping.items() if "create procedure" in key.casefold()), None
        )
        value = None if definition is None else str(definition)
        return StoredProcedureDefinition(
            schema_=None,
            name=name,
            definition=value,
            definition_available=value is not None,
        )
