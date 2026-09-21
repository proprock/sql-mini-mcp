from __future__ import annotations

import base64
from pathlib import Path

import pytest

from sql_safe_mcp.config import load_config
from sql_safe_mcp.errors import DomainError


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


@pytest.mark.parametrize("engine", ["mysql", "mariadb"])
def test_accepts_mysql_family_metadata_servers(tmp_path: Path, engine: str) -> None:
    path = _write(
        tmp_path,
        f"""
version: 1
servers:
  one:
    engine: {engine}
    connection_url: mysql+pymysql://user:password@localhost/database
""",
    )

    assert load_config(path, {}).servers["one"].engine == engine


@pytest.mark.parametrize(
    ("engine", "url"),
    [
        ("mysql", "mssql+pyodbc://u:p@h/d?driver=x"),
        ("mariadb", "mssql+pyodbc://u:p@h/d?driver=x"),
        ("sqlserver", "mysql+pymysql://u:p@h/d"),
    ],
)
def test_rejects_engine_driver_mismatch(tmp_path: Path, engine: str, url: str) -> None:
    path = _write(
        tmp_path,
        f"""
version: 1
servers:
  one:
    engine: {engine}
    connection_url: {url}
""",
    )

    with pytest.raises(DomainError, match="CONFIG_ERROR"):
        load_config(path, {})


@pytest.mark.parametrize("engine", ["mysql", "mariadb"])
@pytest.mark.parametrize(("schema_line", "valid"), [("", True), ("          schema: app\n", False)])
def test_pii_safe_for_mysql_family_forbids_rule_schema(
    tmp_path: Path, engine: str, schema_line: str, valid: bool
) -> None:
    path = _write(
        tmp_path,
        f"""
version: 1
servers:
  one:
    engine: {engine}
    access_level: pii_safe
    connection_url: mysql+pymysql://user:password@localhost/database
    pii_key_env: KEY
    pii:
      rules:
        - database: "*"
{schema_line}          table: users
          columns: [email]
""",
    )
    env = {"KEY": base64.b64encode(b"x" * 32).decode()}

    if valid:
        assert load_config(path, env).servers["one"].access_level == "pii_safe"
    else:
        with pytest.raises(DomainError, match="CONFIG_ERROR"):
            load_config(path, env)


@pytest.mark.parametrize(
    ("yaml_text", "environment"),
    [
        (
            """
version: 2
servers:
  legacy:
    engine: sqlserver
    connection_url: ${URL}
""",
            {"URL": "mssql+pyodbc://u:p@host/master?driver=x"},
        ),
        (
            """
version: 1
servers:
  legacy:
    engine: sqlserver
    connection_url: postgresql://u:p@host/database
""",
            {},
        ),
        (
            """
version: 1
servers:
  legacy:
    engine: sqlserver
    connection_url: ${MISSING_URL}
""",
            {},
        ),
    ],
)
def test_rejects_invalid_version_driver_and_missing_environment(
    tmp_path: Path, yaml_text: str, environment: dict[str, str]
) -> None:
    with pytest.raises(DomainError, match="CONFIG_ERROR"):
        load_config(_write(tmp_path, yaml_text), environment)


def test_rejects_invalid_base64_key(tmp_path: Path) -> None:
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

    with pytest.raises(DomainError, match="valid base64"):
        load_config(path, {"URL": "mssql+pyodbc://u:p@host/master?driver=x", "KEY": "!!!"})


@pytest.mark.parametrize(
    "server_fields",
    [
        "access_level: pii_safe",
        "access_level: metadata\n    pii_key_env: KEY",
    ],
)
def test_rejects_incomplete_or_forbidden_pii_configuration(
    tmp_path: Path, server_fields: str
) -> None:
    path = _write(
        tmp_path,
        f"""
version: 1
servers:
  legacy:
    engine: sqlserver
    connection_url: ${{URL}}
    {server_fields}
""",
    )

    with pytest.raises(DomainError, match="CONFIG_ERROR"):
        load_config(
            path,
            {"URL": "mssql+pyodbc://u:p@host/master?driver=x", "KEY": _key(3)},
        )


def test_validation_error_does_not_echo_secret_extra_field(tmp_path: Path) -> None:
    secret = "do-not-leak-this-token"
    path = _write(
        tmp_path,
        f"""
version: 1
servers:
  legacy:
    engine: sqlserver
    connection_url: mssql+pyodbc://user:password@host/master?driver=x
    accidental_secret: {secret}
""",
    )

    with pytest.raises(DomainError) as raised:
        load_config(path, {})

    message = str(raised.value)
    assert "CONFIG_ERROR" in message
    assert secret not in message
    assert "password" not in message


def test_malformed_yaml_does_not_echo_source_secret(tmp_path: Path) -> None:
    secret = "yaml-secret-value"
    path = _write(tmp_path, f"version: 1\nservers: [\n  {secret}\n")

    with pytest.raises(DomainError) as raised:
        load_config(path, {})

    assert secret not in str(raised.value)


_MINIMAL_SERVER = """
servers:
  reporting:
    engine: sqlserver
    connection_url: mssql+pyodbc://u:p@h/master?driver=x
"""


def test_logging_level_defaults_to_info(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, "version: 1\n" + _MINIMAL_SERVER), {})

    assert config.logging.level == "INFO"


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_logging_level_accepts_standard_levels(tmp_path: Path, level: str) -> None:
    path = _write(tmp_path, f"version: 1\nlogging:\n  level: {level}\n" + _MINIMAL_SERVER)

    assert load_config(path, {}).logging.level == level


@pytest.mark.parametrize("body", ["  level: debug\n", "  level: TRACE\n", "  file: x.log\n"])
def test_logging_rejects_unknown_levels_and_keys(tmp_path: Path, body: str) -> None:
    path = _write(tmp_path, "version: 1\nlogging:\n" + body + _MINIMAL_SERVER)

    with pytest.raises(DomainError) as error:
        load_config(path, {})

    assert "logging" in str(error.value)
