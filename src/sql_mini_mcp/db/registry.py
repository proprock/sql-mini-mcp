from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from threading import RLock
from typing import Any, TypeVar

import anyio
from sqlalchemy import Engine, create_engine, event

from sql_mini_mcp.config import AppConfig
from sql_mini_mcp.errors import DomainError, ErrorCode

T = TypeVar("T")


class EngineRegistry:
    """Thread-safe lazy LRU of SQLAlchemy engines."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._engines: OrderedDict[tuple[str, str | None], Engine] = OrderedDict()
        self._lock = RLock()
        self._limiter = anyio.CapacityLimiter(config.runtime.max_concurrent_db_operations)

    def _create_engine(self, alias: str, database: str | None) -> Engine:
        server = self._config.servers[alias]
        url = server.connection_url.get_secret_value()
        if database is not None:
            from sqlalchemy.engine import make_url

            url = make_url(url).set(database=database)
        engine = create_engine(
            url,
            pool_size=self._config.runtime.pool_size,
            max_overflow=self._config.runtime.max_overflow,
            pool_timeout=self._config.runtime.pool_timeout_seconds,
            pool_pre_ping=True,
            pool_use_lifo=True,
        )
        timeout = self._config.runtime.statement_timeout_seconds

        @event.listens_for(engine, "connect")
        def set_connection_timeout(dbapi_connection: Any, _record: Any) -> None:
            if hasattr(dbapi_connection, "timeout"):
                dbapi_connection.timeout = timeout

        @event.listens_for(engine, "before_cursor_execute")
        def set_statement_timeout(
            _connection: Any,
            cursor: Any,
            _statement: str,
            _parameters: Any,
            _context: Any,
            _executemany: bool,
        ) -> None:
            if hasattr(cursor, "timeout"):
                cursor.timeout = timeout

        return engine

    def get(self, alias: str, database: str | None = None) -> Engine:
        if alias not in self._config.servers:
            raise DomainError(ErrorCode.UNKNOWN_SERVER, f"Unknown configured server {alias!r}.")
        key = (alias, database)
        evicted: Engine | None = None
        with self._lock:
            if engine := self._engines.get(key):
                self._engines.move_to_end(key)
                return engine
            engine = self._create_engine(alias, database)
            self._engines[key] = engine
            if len(self._engines) > self._config.runtime.engine_cache_size:
                _, evicted = self._engines.popitem(last=False)
        if evicted is not None:
            evicted.dispose()
        return engine

    async def run(
        self,
        alias: str,
        database: str | None,
        operation: Callable[[Engine], T],
    ) -> T:
        engine = self.get(alias, database)
        return await anyio.to_thread.run_sync(operation, engine, limiter=self._limiter)

    def dispose(self) -> None:
        with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
        for engine in engines:
            engine.dispose()

    @property
    def cached_engine_count(self) -> int:
        with self._lock:
            return len(self._engines)
