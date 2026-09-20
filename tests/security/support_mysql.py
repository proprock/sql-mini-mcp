"""MySQL/MariaDB counterpart of the shared harness: schema-less catalog, mysql aliases."""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import ClassVar, cast

from support import ALIAS, KEY, OTHER_KEY, SpyConnection, _SpyRegistry

from sql_mini_mcp.config import AppConfig
from sql_mini_mcp.db.registry import EngineRegistry
from sql_mini_mcp.service import DatabaseService


class MysqlCatalog:
    """MySQL has no schema level: reflection reports an empty schema for every table."""

    tables: ClassVar[dict[str, list[str]]] = {
        "users": ["id", "email", "phone", "name"],
        "orders": ["id", "user_id", "total"],
        "canary": ["id"],
    }

    def list_tables(self) -> list[tuple[str, str]]:
        return [("", name) for name in self.tables]

    def columns(self, schema: str, table: str) -> Sequence[str]:
        assert schema == ""
        return self.tables[table]


def mysql_config(engine: str = "mysql") -> AppConfig:
    def server(key: bytes, key_env: str) -> dict[str, object]:
        return {
            "engine": engine,
            "access_level": "pii_safe",
            "connection_url": "mysql+pymysql://u:p@db/app",
            "pii_key_env": key_env,
            "pii_key": base64.b64encode(key).decode(),
            "pii": {
                "rules": [
                    {"database": "*", "table": "users", "columns": ["email", "phone"]},
                    {"database": "app", "table": "orders", "columns": ["total"]},
                ]
            },
        }

    return AppConfig.model_validate(
        {"version": 1, "servers": {ALIAS: server(KEY, "K1"), "other": server(OTHER_KEY, "K2")}}
    )


def spy_mysql_service(connection: SpyConnection, engine: str = "mysql") -> DatabaseService:
    return DatabaseService(
        mysql_config(engine),
        cast(EngineRegistry, _SpyRegistry(connection)),
        catalog_factory=lambda *_: MysqlCatalog(),
    )
