from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from sql_mini_mcp.config import AppConfig, RuntimeConfig, ServerConfig
from sql_mini_mcp.db.registry import EngineRegistry


def _config(cache_size: int = 1, concurrency: int = 8) -> AppConfig:
    return AppConfig(
        version=1,
        runtime=RuntimeConfig(
            engine_cache_size=cache_size,
            max_concurrent_db_operations=concurrency,
        ),
        servers={
            "one": ServerConfig(
                engine="sqlserver",
                connection_url=SecretStr("mssql+pyodbc://u:p@one/master?driver=x"),
            )
        },
    )


def test_registry_is_lazy_and_disposes_evicted_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    created = [Mock(), Mock()]
    monkeypatch.setattr("sql_mini_mcp.db.registry.create_engine", Mock(side_effect=created))
    monkeypatch.setattr("sql_mini_mcp.db.registry.event.listens_for", lambda *_args: lambda fn: fn)
    registry = EngineRegistry(_config())

    assert registry.cached_engine_count == 0
    assert registry.get("one", "db1") is created[0]
    assert registry.get("one", "db2") is created[1]

    created[0].dispose.assert_called_once_with()
    assert registry.cached_engine_count == 1


def test_registry_reuses_same_alias_and_database(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Mock()
    create = Mock(return_value=engine)
    monkeypatch.setattr("sql_mini_mcp.db.registry.create_engine", create)
    monkeypatch.setattr("sql_mini_mcp.db.registry.event.listens_for", lambda *_args: lambda fn: fn)
    registry = EngineRegistry(_config())

    assert registry.get("one", "db") is registry.get("one", "db")
    create.assert_called_once()


def test_registry_dispose_closes_all_cached_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    engines = [Mock(), Mock()]
    monkeypatch.setattr("sql_mini_mcp.db.registry.create_engine", Mock(side_effect=engines))
    monkeypatch.setattr("sql_mini_mcp.db.registry.event.listens_for", lambda *_args: lambda fn: fn)
    registry = EngineRegistry(_config(cache_size=2))
    registry.get("one", "db1")
    registry.get("one", "db2")

    registry.dispose()

    assert registry.cached_engine_count == 0
    for engine in engines:
        engine.dispose.assert_called_once_with()


def test_registry_limits_concurrent_database_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Mock()
    monkeypatch.setattr("sql_mini_mcp.db.registry.create_engine", Mock(return_value=engine))
    monkeypatch.setattr("sql_mini_mcp.db.registry.event.listens_for", lambda *_args: lambda fn: fn)
    registry = EngineRegistry(_config(concurrency=2))
    lock = threading.Lock()
    active = 0
    peak = 0

    def operation(_engine: object) -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1

    async def scenario() -> None:
        await asyncio.gather(*(registry.run("one", "db", operation) for _ in range(6)))

    asyncio.run(scenario())

    assert peak == 2
