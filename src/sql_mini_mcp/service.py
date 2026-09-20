from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError

from sql_mini_mcp.config import AppConfig, ServerConfig
from sql_mini_mcp.db.extras import extras_for
from sql_mini_mcp.db.reflection import get_table_definition as reflect_table_definition
from sql_mini_mcp.db.reflection import list_tables as reflect_tables
from sql_mini_mcp.db.registry import EngineRegistry
from sql_mini_mcp.errors import DomainError, ErrorCode
from sql_mini_mcp.models import (
    DatabaseList,
    DatabaseSummary,
    ServerList,
    ServerSummary,
    StoredProcedureDefinition,
    StoredProcedureList,
    StoredProcedureSummary,
    TableDefinition,
    TableList,
    TableSummary,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _contains(value: str, needle: str | None) -> bool:
    return needle is None or needle.casefold() in value.casefold()


class DatabaseService:
    def __init__(self, config: AppConfig, registry: EngineRegistry) -> None:
        self.config = config
        self.registry = registry

    def _server(self, alias: str) -> ServerConfig:
        try:
            return self.config.servers[alias]
        except KeyError as exc:
            raise DomainError(
                ErrorCode.UNKNOWN_SERVER,
                f"Unknown configured server {alias!r}.",
                "Call list_servers to discover configured aliases.",
            ) from exc

    async def _run(self, alias: str, database: str | None, operation: Callable[[Engine], T]) -> T:
        self._server(alias)
        try:
            return await self.registry.run(alias, database, operation)
        except DomainError:
            raise
        except OperationalError as exc:
            raise DomainError(
                ErrorCode.CONNECTION_FAILED,
                "Could not connect to the configured database server.",
                retryable=True,
            ) from exc
        except DBAPIError as exc:
            message = str(exc.orig).casefold()
            if "timeout" in message:
                raise DomainError(
                    ErrorCode.TIMEOUT, "The database operation timed out.", retryable=True
                ) from exc
            if any(value in message for value in ("permission", "denied", "login failed")):
                raise DomainError(
                    ErrorCode.ACCESS_DENIED, "The database denied this operation."
                ) from exc
            error = DomainError.unexpected()
            logger.error("Database operation failed; reference=%s", error.correlation_id)
            raise error from exc
        except SQLAlchemyError as exc:
            error = DomainError.unexpected()
            logger.error("SQLAlchemy operation failed; reference=%s", error.correlation_id)
            raise error from exc
        except Exception as exc:
            error = DomainError.unexpected()
            logger.error(
                "Unexpected database operation failure; reference=%s", error.correlation_id
            )
            raise error from exc

    def list_servers(self) -> ServerList:
        return ServerList(
            servers=[
                ServerSummary(name=alias, engine=server.engine, access_level=server.access_level)
                for alias, server in sorted(
                    self.config.servers.items(), key=lambda item: item[0].casefold()
                )
            ]
        )

    async def list_databases(self, server: str, name_contains: str | None = None) -> DatabaseList:
        configured = self._server(server)

        def operation(engine: Engine) -> list[str]:
            with engine.connect() as connection:
                return extras_for(configured.engine).list_databases(connection)

        names = await self._run(server, None, operation)
        return DatabaseList(
            databases=[
                DatabaseSummary(name=name)
                for name in sorted(names, key=str.casefold)
                if _contains(name, name_contains)
            ]
        )

    async def list_tables(
        self,
        server: str,
        database: str,
        schema: str | None = None,
        name_contains: str | None = None,
    ) -> TableList:
        self._server(server)

        def operation(engine: Engine) -> list[TableSummary]:
            with engine.connect() as connection:
                return reflect_tables(connection)

        tables = await self._run(server, database, operation)
        selected = [
            table
            for table in tables
            if (schema is None or (table.schema_ or "").casefold() == schema.casefold())
            and _contains(table.name, name_contains)
        ]
        selected.sort(key=lambda table: ((table.schema_ or "").casefold(), table.name.casefold()))
        return TableList(tables=selected)

    @staticmethod
    def _resolve_table(tables: list[TableSummary], table: str, schema: str | None) -> TableSummary:
        matches = [
            item
            for item in tables
            if item.name.casefold() == table.casefold()
            and (schema is None or (item.schema_ or "").casefold() == schema.casefold())
        ]
        if not matches:
            raise DomainError(ErrorCode.NOT_FOUND, f"Table {table!r} was not found.")
        if len(matches) > 1:
            candidates = ", ".join(f"{item.schema_}.{item.name}" for item in matches)
            raise DomainError(
                ErrorCode.AMBIGUOUS_OBJECT,
                f"Table {table!r} is ambiguous.",
                f"Specify schema; candidates: {candidates}.",
            )
        return matches[0]

    async def get_table_definition(
        self, server: str, database: str, table: str, schema: str | None = None
    ) -> TableDefinition:
        self._server(server)

        def operation(engine: Engine) -> TableDefinition:
            with engine.connect() as connection:
                selected = self._resolve_table(reflect_tables(connection), table, schema)
                return reflect_table_definition(connection, selected.schema_, selected.name)

        return await self._run(server, database, operation)

    async def list_stored_procedures(
        self,
        server: str,
        database: str,
        schema: str | None = None,
        name_contains: str | None = None,
    ) -> StoredProcedureList:
        configured = self._server(server)

        def operation(engine: Engine) -> list[StoredProcedureSummary]:
            with engine.connect() as connection:
                return extras_for(configured.engine).list_stored_procedures(connection, database)

        procedures = await self._run(server, database, operation)
        selected = [
            item
            for item in procedures
            if (schema is None or (item.schema_ or "").casefold() == schema.casefold())
            and _contains(item.name, name_contains)
        ]
        selected.sort(key=lambda item: ((item.schema_ or "").casefold(), item.name.casefold()))
        return StoredProcedureList(stored_procedures=selected)

    async def get_stored_procedure(
        self,
        server: str,
        database: str,
        name: str,
        schema: str | None = None,
    ) -> StoredProcedureDefinition:
        configured = self._server(server)
        listing = await self.list_stored_procedures(server, database, schema)
        matches = [
            item for item in listing.stored_procedures if item.name.casefold() == name.casefold()
        ]
        if not matches:
            raise DomainError(ErrorCode.NOT_FOUND, f"Stored procedure {name!r} was not found.")
        if len(matches) > 1:
            candidates = ", ".join(f"{item.schema_}.{item.name}" for item in matches)
            raise DomainError(
                ErrorCode.AMBIGUOUS_OBJECT,
                f"Stored procedure {name!r} is ambiguous.",
                f"Specify schema; candidates: {candidates}.",
            )
        selected = matches[0]

        def operation(engine: Engine) -> StoredProcedureDefinition | None:
            with engine.connect() as connection:
                return extras_for(configured.engine).get_stored_procedure(
                    connection, database, selected.schema_, selected.name
                )

        result = await self._run(server, database, operation)
        if result is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"Stored procedure {name!r} was not found.")
        if (
            result.definition is not None
            and len(result.definition) > self.config.runtime.max_definition_chars
        ):
            raise DomainError(
                ErrorCode.DEFINITION_TOO_LARGE,
                "Stored procedure definition exceeds the configured response limit.",
            )
        return result
