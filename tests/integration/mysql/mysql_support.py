from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

from sql_mini_mcp.config import AppConfig, RuntimeConfig, ServerConfig

Engine = Literal["mysql", "mariadb"]

_ENV = {
    "mysql": "SQL_MINI_MCP_TEST_MYSQL_URL",
    "mariadb": "SQL_MINI_MCP_TEST_MARIADB_URL",
}


@dataclass(frozen=True, slots=True)
class LiveMySql:
    engine: Engine
    admin_url: URL
    config: AppConfig
    database: str


def build_config(
    engine: Engine, admin_url: URL, database: str, logins: dict[str, tuple[str, str]], timeout: int
) -> AppConfig:
    return AppConfig(
        version=1,
        runtime=RuntimeConfig(statement_timeout_seconds=timeout, pool_timeout_seconds=5),
        servers={
            alias: ServerConfig(
                engine=engine,
                connection_url=SecretStr(
                    admin_url.set(
                        username=login, password=password, database=database
                    ).render_as_string(hide_password=False)
                ),
            )
            for alias, (login, password) in logins.items()
        },
    )


def _run(url: URL, statements: list[str]) -> None:
    # Raw DBAPI cursor: SQLAlchemy would apply %-formatting to statements such as '%' hosts.
    engine = create_engine(url)
    try:
        raw = engine.raw_connection()
        try:
            cursor = raw.cursor()
            for statement in statements:
                cursor.execute(statement)
            raw.commit()
        finally:
            raw.close()
    finally:
        engine.dispose()


@pytest.fixture(scope="module", params=["mysql", "mariadb"])
def live_mysql(request: pytest.FixtureRequest) -> Iterator[LiveMySql]:
    engine: Engine = request.param
    raw_url = os.environ.get(_ENV[engine])
    if not raw_url:
        pytest.skip(f"{_ENV[engine]} is not configured")
    admin_url = make_url(raw_url)

    suffix = uuid4().hex[:12]
    database = f"smm_{suffix}"
    logins = {
        "app": (f"smm_app_{suffix}", uuid4().hex),
        "hidden": (f"smm_hidden_{suffix}", uuid4().hex),
        "denied": (f"smm_denied_{suffix}", uuid4().hex),
    }
    grants = {
        "app": f"GRANT ALL ON `{database}`.* TO '{{login}}'@'%'",
        "hidden": f"GRANT SELECT, EXECUTE ON `{database}`.* TO '{{login}}'@'%'",
    }
    cleanup = [f"DROP DATABASE IF EXISTS `{database}`"] + [
        f"DROP USER IF EXISTS '{login}'@'%'" for login, _ in logins.values()
    ]
    _run(admin_url, cleanup)
    try:
        app_login = logins["app"][0]
        setup = [f"CREATE DATABASE `{database}`"]
        for alias, (login, password) in logins.items():
            setup.append(f"CREATE USER '{login}'@'%' IDENTIFIED BY '{password}'")
            if alias in grants:
                setup.append(grants[alias].format(login=login))
        setup += [
            f"""CREATE TABLE `{database}`.`users` (
                tenant_id INT NOT NULL,
                id BIGINT NOT NULL,
                parent_id BIGINT NULL,
                email VARCHAR(120) NOT NULL,
                amount DECIMAL(12, 2) NULL,
                created DATETIME(3) NULL,
                PRIMARY KEY (tenant_id, id),
                UNIQUE KEY uq_users_email (tenant_id, email),
                KEY ix_users_email (email),
                CONSTRAINT fk_users_parent FOREIGN KEY (tenant_id, parent_id)
                    REFERENCES `{database}`.`users` (tenant_id, id)
            ) ENGINE=InnoDB""",
            f"CREATE TABLE `{database}`.`audit_events` (id INT PRIMARY KEY, note TEXT)",
            # Only the definer sees a routine body; the other logins get NULL.
            f"CREATE DEFINER='{app_login}'@'%' PROCEDURE `{database}`.`visible_proc`() "
            "BEGIN SELECT 1; END",
            f"CREATE DEFINER='{app_login}'@'%' PROCEDURE `{database}`.`other_proc`() "
            "BEGIN SELECT 2; END",
        ]
        _run(admin_url, setup)
        yield LiveMySql(
            engine=engine,
            admin_url=admin_url,
            config=build_config(engine, admin_url, database, logins, timeout=2),
            database=database,
        )
    finally:
        _run(admin_url, cleanup)
