from __future__ import annotations

import base64
import binascii
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from sqlalchemy.engine import make_url

from sql_mini_mcp.errors import DomainError, ErrorCode

_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
_FULL_ENV_PATTERN = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)\}$")


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_concurrent_db_operations: int = Field(default=8, ge=1, le=128)
    engine_cache_size: int = Field(default=32, ge=1, le=1024)
    pool_size: int = Field(default=2, ge=1, le=32)
    max_overflow: int = Field(default=2, ge=0, le=64)
    pool_timeout_seconds: int = Field(default=10, ge=1, le=300)
    statement_timeout_seconds: int = Field(default=30, ge=1, le=3600)
    max_definition_chars: int = Field(default=262_144, ge=1024, le=10_000_000)
    default_max_rows: int = Field(default=200, ge=1, le=100_000)
    hard_max_rows: int = Field(default=1000, ge=1, le=100_000)
    max_sql_chars: int = Field(default=65_536, ge=256, le=1_000_000)
    max_ast_nodes: int = Field(default=2000, ge=10, le=100_000)
    max_joins: int = Field(default=8, ge=0, le=100)
    max_in_list_items: int = Field(default=500, ge=1, le=100_000)

    @model_validator(mode="after")
    def validate_row_limits(self) -> RuntimeConfig:
        if self.default_max_rows > self.hard_max_rows:
            raise ValueError("default_max_rows cannot exceed hard_max_rows")
        return self


class PiiRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: str = Field(min_length=1)
    schema_: str | None = Field(default=None, alias="schema")
    table: str = Field(min_length=1)
    columns: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_wildcards(self) -> PiiRule:
        if "*" in self.table or (self.schema_ and "*" in self.schema_):
            raise ValueError("wildcards are allowed only in pii rule database")
        if self.database != "*" and "*" in self.database:
            raise ValueError("database must be an exact name or '*'")
        folded = [column.casefold() for column in self.columns]
        if len(folded) != len(set(folded)):
            raise ValueError("pii rule columns must be unique")
        return self


class PiiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[PiiRule] = Field(min_length=1)


_DRIVERNAMES = {
    "sqlserver": "mssql+pyodbc",
    "mysql": "mysql+pymysql",
    "mariadb": "mysql+pymysql",
}


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["sqlserver", "mysql", "mariadb"]
    access_level: Literal["metadata", "pii_safe"] = "metadata"
    connection_url: SecretStr
    pii_key_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]*$")
    pii: PiiConfig | None = None
    pii_key: SecretStr | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def validate_security_shape(self) -> ServerConfig:
        if self.access_level == "pii_safe":
            if self.engine != "sqlserver":
                raise ValueError(f"pii_safe is not supported for engine {self.engine!r}")
            if not self.pii_key_env or self.pii is None:
                raise ValueError("pii_safe servers require pii_key_env and pii rules")
        elif self.pii_key_env is not None or self.pii is not None:
            raise ValueError("metadata servers cannot configure pii_key_env or pii rules")

        driver = make_url(self.connection_url.get_secret_value()).drivername
        expected = _DRIVERNAMES[self.engine]
        if driver != expected:
            raise ValueError(f"engine {self.engine!r} requires SQLAlchemy dialect {expected!r}")
        return self

    def key_bytes(self) -> bytes | None:
        if self.pii_key is None:
            return None
        return base64.b64decode(self.pii_key.get_secret_value(), validate=True)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    servers: dict[str, ServerConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_aliases_and_keys(self) -> AppConfig:
        seen_keys: dict[bytes, str] = {}
        for alias, server in self.servers.items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", alias):
                raise ValueError(f"invalid server alias {alias!r}")
            key = server.key_bytes()
            if key is None:
                continue
            if len(key) != 32:
                raise ValueError(f"PII key for server {alias!r} must decode to 32 bytes")
            if previous := seen_keys.get(key):
                raise ValueError(
                    f"PII keys must be unique per server alias; {alias!r} duplicates {previous!r}"
                )
            seen_keys[key] = alias
        return self


def _expand_connection_url(template: str, environ: Mapping[str, str]) -> str:
    full_match = _FULL_ENV_PATTERN.fullmatch(template)
    if full_match:
        name = full_match.group(1)
        if name not in environ:
            raise ValueError(f"missing environment variable {name}")
        return environ[name]

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in environ:
            raise ValueError(f"missing environment variable {name}")
        return quote(environ[name], safe="")

    expanded = _ENV_PATTERN.sub(replace, template)
    if "${" in expanded:
        raise ValueError("invalid environment placeholder in connection_url")
    return expanded


def _validation_summary(error: ValidationError) -> str:
    issues: list[str] = []
    for issue in error.errors(include_url=False, include_context=False, include_input=False):
        location = ".".join(str(part) for part in issue["loc"])
        issues.append(f"{location}: {issue['msg']}" if location else str(issue["msg"]))
    return "; ".join(issues)


def load_config(path: str | Path, environ: Mapping[str, str] | None = None) -> AppConfig:
    env = os.environ if environ is None else environ
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("configuration root must be a mapping")
        servers = raw.get("servers")
        if not isinstance(servers, dict):
            raise ValueError("servers must be a mapping")
        for alias, value in servers.items():
            if not isinstance(value, dict):
                raise ValueError(f"server {alias!r} must be a mapping")
            url = value.get("connection_url")
            if not isinstance(url, str):
                raise ValueError(f"server {alias!r} requires connection_url")
            value["connection_url"] = _expand_connection_url(url, env)
            key_env = value.get("pii_key_env")
            if key_env is not None:
                if not isinstance(key_env, str) or key_env not in env:
                    raise ValueError(f"missing PII key environment variable {key_env!r}")
                try:
                    decoded = base64.b64decode(env[key_env], validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise ValueError(f"PII key for server {alias!r} is not valid base64") from exc
                if len(decoded) != 32:
                    raise ValueError(f"PII key for server {alias!r} must decode to 32 bytes")
                value["pii_key"] = env[key_env]
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise DomainError(
            ErrorCode.CONFIG_ERROR,
            f"Invalid configuration: {_validation_summary(exc)}",
        ) from exc
    except (OSError, yaml.YAMLError) as exc:
        raise DomainError(ErrorCode.CONFIG_ERROR, "Invalid configuration file.") from exc
    except ValueError as exc:
        raise DomainError(ErrorCode.CONFIG_ERROR, f"Invalid configuration: {exc}") from exc
