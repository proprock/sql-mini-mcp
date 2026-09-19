from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, inspect, text

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    url = os.environ.get("SQL_MINI_MCP_TEST_SQLSERVER_URL")
    if not url:
        pytest.skip("SQL_MINI_MCP_TEST_SQLSERVER_URL is not configured")
    value = create_engine(url, pool_pre_ping=True)
    try:
        yield value
    finally:
        value.dispose()


def test_live_reflection_and_writable_canary(engine: Engine) -> None:
    """The opt-in URL must point at a disposable, writable test database."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "IF OBJECT_ID('dbo.SqlMiniMcpCanary', 'U') IS NULL "
                "CREATE TABLE dbo.SqlMiniMcpCanary ("
                "Id int IDENTITY PRIMARY KEY, Email nvarchar(100) NOT NULL UNIQUE)"
            )
        )
        connection.execute(text("DELETE FROM dbo.SqlMiniMcpCanary"))
        connection.execute(
            text("INSERT INTO dbo.SqlMiniMcpCanary (Email) VALUES (:email)"),
            {"email": "SQL_MINI_MCP_PII_CANARY"},
        )

    inspector = inspect(engine)
    columns = inspector.get_columns("SqlMiniMcpCanary", schema="dbo")
    assert [column["name"] for column in columns] == ["Id", "Email"]

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM dbo.SqlMiniMcpCanary")) == 1
