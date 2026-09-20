from __future__ import annotations

import base64
from pathlib import Path

import pytest

from sql_mini_mcp.config import load_config
from sql_mini_mcp.errors import DomainError


def _key(byte: int) -> str:
    return base64.b64encode(bytes([byte]) * 32).decode()


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_embedded_environment_values_with_url_encoding(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
version: 1
servers:
  legacy:
    engine: sqlserver
    connection_url: mssql+pyodbc://${USER}:${PASSWORD}@${HOST}/master?driver=ODBC+Driver+18+for+SQL+Server
""",
    )

    config = load_config(path, {"USER": "a@b", "PASSWORD": "p:/x", "HOST": "sql01"})

    url = config.servers["legacy"].connection_url.get_secret_value()
    assert "a%40b" in url
    assert "p%3A%2Fx" in url


def test_whole_environment_value_may_contain_complete_url(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
version: 1
servers:
  reporting:
    engine: sqlserver
    connection_url: ${REPORTING_SQL_URL}
""",
    )
    expected = "mssql+pyodbc://user:password@sql01/master?driver=ODBC+Driver+18+for+SQL+Server"

    config = load_config(path, {"REPORTING_SQL_URL": expected})

    assert config.servers["reporting"].connection_url.get_secret_value() == expected


def test_pii_key_is_per_server_and_secret_is_redacted(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
version: 1
servers:
  legacy:
    engine: sqlserver
    access_level: pii_safe
    connection_url: ${URL}
    pii_key_env: LEGACY_KEY
    pii:
      rules:
        - database: "*"
          schema: dbo
          table: Users
          columns: [Email]
""",
    )
    config = load_config(
        path,
        {
            "URL": "mssql+pyodbc://user:password@sql01/master?driver=ODBC+Driver+18+for+SQL+Server",
            "LEGACY_KEY": _key(1),
        },
    )

    server = config.servers["legacy"]
    assert server.key_bytes() == bytes([1]) * 32
    assert "password" not in repr(config)
    assert _key(1) not in repr(config)


def test_rejects_reused_key_across_server_aliases(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
version: 1
servers:
  one:
    engine: sqlserver
    access_level: pii_safe
    connection_url: ${URL_ONE}
    pii_key_env: KEY_ONE
    pii: {rules: [{database: "*", schema: dbo, table: Users, columns: [Email]}]}
  two:
    engine: sqlserver
    access_level: pii_safe
    connection_url: ${URL_TWO}
    pii_key_env: KEY_TWO
    pii: {rules: [{database: "*", schema: dbo, table: Users, columns: [Email]}]}
""",
    )
    env = {
        "URL_ONE": "mssql+pyodbc://u:p@one/master?driver=x",
        "URL_TWO": "mssql+pyodbc://u:p@two/master?driver=x",
        "KEY_ONE": _key(2),
        "KEY_TWO": _key(2),
    }

    with pytest.raises(DomainError, match="unique per server alias"):
        load_config(path, env)


@pytest.mark.parametrize("length", [0, 16, 31, 33])
def test_rejects_wrong_key_size(tmp_path: Path, length: int) -> None:
    path = _write(
        tmp_path,
        """
version: 1
servers:
  legacy:
    engine: sqlserver
    access_level: pii_safe
    connection_url: ${URL}
    pii_key_env: KEY
    pii: {rules: [{database: "*", schema: dbo, table: Users, columns: [Email]}]}
""",
    )
    env = {
        "URL": "mssql+pyodbc://u:p@one/master?driver=x",
        "KEY": base64.b64encode(b"x" * length).decode(),
    }

    with pytest.raises(DomainError, match="32 bytes"):
        load_config(path, env)


def test_rejects_mysql_until_milestone_3(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
version: 1
servers:
  future:
    engine: mysql
    connection_url: mysql+pymysql://user:password@localhost/database
""",
    )

    with pytest.raises(DomainError, match="CONFIG_ERROR"):
        load_config(path, {})
