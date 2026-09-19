from __future__ import annotations

from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from sql_mini_mcp.config import AppConfig, RuntimeConfig, ServerConfig
from sql_mini_mcp.db.registry import EngineRegistry


def _config(cache_size: int = 1) -> AppConfig:
    return AppConfig(
        version=1,
        runtime=RuntimeConfig(engine_cache_size=cache_size),
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
