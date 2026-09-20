"""Exact error behavior of configuration loading and PII key handling."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from pydantic import ValidationError

from sql_mini_mcp.config import AppConfig, load_config
from sql_mini_mcp.errors import DomainError, ErrorCode

URL = "mssql+pyodbc://u:p@sql/master?driver=x"


def _yaml(url: str = URL, extra: str = "", version: int = 1) -> str:
    return (
        f"version: {version}\n"
        "servers:\n"
        "  s:\n"
        "    engine: sqlserver\n"
        f"    connection_url: {url}\n"
        f"{extra}"
    )


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _error(path: Path, env: dict[str, str] | None = None) -> DomainError:
    with pytest.raises(DomainError) as info:
        load_config(path, {} if env is None else env)
    assert info.value.code is ErrorCode.CONFIG_ERROR
    return info.value


def test_missing_file_is_a_generic_config_error(tmp_path: Path) -> None:
    error = _error(tmp_path / "absent.yaml")
    assert error.public_message == "Invalid configuration file."
    assert error.hint is None


def test_malformed_yaml_is_a_generic_config_error(tmp_path: Path) -> None:
    assert _error(_write(tmp_path, "a: [unclosed")).public_message == "Invalid configuration file."


def test_embedded_missing_environment_variable_is_named(tmp_path: Path) -> None:
    error = _error(_write(tmp_path, _yaml(URL + "${SECRET}")))
    assert error.public_message == "Invalid configuration: missing environment variable SECRET"


def test_whole_value_missing_environment_variable_is_named(tmp_path: Path) -> None:
    error = _error(_write(tmp_path, _yaml("${SECRET_URL}")))
    assert error.public_message == "Invalid configuration: missing environment variable SECRET_URL"


def test_unresolvable_placeholder_is_rejected(tmp_path: Path) -> None:
    error = _error(_write(tmp_path, _yaml(URL + "${lower}")))
    assert error.public_message == (
        "Invalid configuration: invalid environment placeholder in connection_url"
    )


def test_special_characters_in_embedded_values_are_encoded(tmp_path: Path) -> None:
    path = _write(tmp_path, _yaml("mssql+pyodbc://u:${P}@h/d?driver=x"))
    config = load_config(path, {"P": "Xa/b c@d?e#f%g&h=i+j"})
    url = config.servers["s"].connection_url.get_secret_value()
    assert ":Xa%2Fb%20c%40d%3Fe%23f%25g%26h%3Di%2Bj@h" in url


def test_process_environment_is_used_when_none_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMM_TEST_HOST", "envhost")
    path = _write(tmp_path, _yaml("mssql+pyodbc://u:p@${SMM_TEST_HOST}/d?driver=x"))
    config = load_config(path)
    assert "envhost" in config.servers["s"].connection_url.get_secret_value()


def test_non_ascii_configuration_is_read_as_utf8(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_bytes(("# caf\u00e9 \u4e2d\u6587\n" + _yaml()).encode("utf-8"))
    assert "s" in load_config(path, {}).servers


def test_validation_errors_list_each_location_and_message(tmp_path: Path) -> None:
    error = _error(_write(tmp_path, _yaml(extra="    bogus: 1\n", version=2)))
    assert error.public_message == (
        "Invalid configuration: version: Input should be 1; "
        "servers.s.bogus: Extra inputs are not permitted"
    )


def test_non_string_pii_key_env_is_a_config_error_not_a_crash(tmp_path: Path) -> None:
    error = _error(_write(tmp_path, _yaml(extra="    pii_key_env: 5\n")), {"5": "x"})
    assert error.public_message.startswith("Invalid configuration: missing PII key environment")


def test_a_missing_pii_key_variable_is_named_without_its_value(tmp_path: Path) -> None:
    error = _error(_write(tmp_path, _yaml(extra="    pii_key_env: NOPE\n")))
    assert error.public_message == (
        "Invalid configuration: missing PII key environment variable 'NOPE'"
    )


def _model(key: str) -> dict[str, object]:
    return {
        "version": 1,
        "servers": {
            "s": {
                "engine": "sqlserver",
                "access_level": "pii_safe",
                "connection_url": URL,
                "pii_key_env": "K",
                "pii": {"rules": [{"database": "*", "table": "T", "columns": ["c"]}]},
                "pii_key": key,
            }
        },
    }


def test_pii_key_must_be_strict_base64() -> None:
    good = base64.b64encode(bytes(range(32))).decode()
    AppConfig.model_validate(_model(good))
    noisy = good[:10] + "!" + good[10:]
    with pytest.raises(ValidationError):
        AppConfig.model_validate(_model(noisy))


def test_pii_key_must_decode_to_exactly_32_bytes() -> None:
    for size in (31, 33, 16, 64):
        key = base64.b64encode(bytes(size)).decode()
        with pytest.raises(ValidationError):
            AppConfig.model_validate(_model(key))


def test_duplicate_keys_across_aliases_are_rejected() -> None:
    key = base64.b64encode(bytes(range(32))).decode()
    model = _model(key)
    servers = model["servers"]
    assert isinstance(servers, dict)
    servers["t"] = dict(servers["s"])
    with pytest.raises(ValidationError, match="must be unique per server alias"):
        AppConfig.model_validate(model)
