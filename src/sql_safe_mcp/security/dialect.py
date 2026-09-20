from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SqlDialect:
    """Everything the shared validation pipeline needs to know about one SQL dialect.

    Policy, tokens, and ValidatedQuery are dialect-independent; only these facts differ. The
    dialect always comes from the trusted server configuration, never from the caller.
    """

    name: str  # SQLGlot dialect used to parse and to generate SQL
    has_schema: bool  # False when a database is the catalog and objects have no schema level
    bind_marker: str  # DBAPI positional marker written into generated SQL
    escape_percent: bool  # the driver applies %-formatting, so a literal % must be doubled


SQLSERVER = SqlDialect(name="tsql", has_schema=True, bind_marker="?", escape_percent=False)
MYSQL = SqlDialect(name="mysql", has_schema=False, bind_marker="%s", escape_percent=True)


def dialect_for(engine: str) -> SqlDialect:
    if engine == "sqlserver":
        return SQLSERVER
    if engine in ("mysql", "mariadb"):
        return MYSQL
    raise ValueError(f"unsupported engine {engine!r}")
