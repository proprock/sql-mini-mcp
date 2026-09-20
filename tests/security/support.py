"""Shared harness for the security tests: catalog, config, spy database, query generators."""

from __future__ import annotations

import base64
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, cast

from hypothesis import strategies as st

from sql_mini_mcp.config import AppConfig, PiiConfig, PiiRule, RuntimeConfig
from sql_mini_mcp.db.registry import EngineRegistry
from sql_mini_mcp.security.pipeline import validate_sql
from sql_mini_mcp.security.tokens import TokenCodec
from sql_mini_mcp.security.validated_query import ValidatedQuery
from sql_mini_mcp.service import DatabaseService

KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))
ALIAS = "srv"
DATABASE = "app"
OWN = TokenCodec(ALIAS, KEY)
FOREIGN = TokenCodec("other", OTHER_KEY)
RUNTIME = RuntimeConfig()
PII = PiiConfig(
    rules=[
        PiiRule(database="*", schema="dbo", table="Users", columns=["Email", "Phone"]),
        PiiRule(database=DATABASE, schema="dbo", table="Orders", columns=["Total"]),
    ]
)


class Catalog:
    tables: ClassVar[dict[tuple[str, str], list[str]]] = {
        ("dbo", "Users"): ["Id", "Email", "Phone", "Name"],
        ("dbo", "Orders"): ["Id", "UserId", "Total"],
        ("dbo", "Contacts"): ["Id", "Email"],
        ("dbo", "Canary"): ["Id"],
        ("dbo", "Items"): ["Id"],
        ("sales", "Items"): ["Id"],
    }

    def list_tables(self) -> list[tuple[str, str]]:
        return list(self.tables)

    def columns(self, schema: str, table: str) -> Sequence[str]:
        return self.tables[(schema, table)]


def validate(sql: str, max_rows: int = 200) -> ValidatedQuery:
    return validate_sql(
        sql,
        alias=ALIAS,
        database=DATABASE,
        catalog=Catalog(),
        pii_config=PII,
        codec=OWN,
        runtime=RUNTIME,
        max_rows=max_rows,
    )


def app_config() -> AppConfig:
    def server(key: bytes, key_env: str) -> dict[str, object]:
        return {
            "engine": "sqlserver",
            "access_level": "pii_safe",
            "connection_url": "mssql+pyodbc://u:p@sql/master?driver=x",
            "pii_key_env": key_env,
            "pii_key": base64.b64encode(key).decode(),
            "pii": {
                "rules": [
                    {
                        "database": "*",
                        "schema": "dbo",
                        "table": "Users",
                        "columns": ["Email", "Phone"],
                    },
                    {
                        "database": DATABASE,
                        "schema": "dbo",
                        "table": "Orders",
                        "columns": ["Total"],
                    },
                ]
            },
        }

    return AppConfig.model_validate(
        {
            "version": 1,
            "servers": {ALIAS: server(KEY, "K1"), "other": server(OTHER_KEY, "K2")},
        }
    )


class SpyResult:
    def __init__(self, keys: Sequence[str] = (), rows: Sequence[tuple[Any, ...]] = ()) -> None:
        self._keys = list(keys)
        self._rows = list(rows)

    def keys(self) -> list[str]:
        return self._keys

    def fetchmany(self, size: int) -> list[Any]:
        return self._rows[:size]

    def close(self) -> None:
        return None


class SpyConnection:
    """Records every statement that reaches the driver."""

    def __init__(self, result: SpyResult | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.result = result or SpyResult()

    def exec_driver_sql(self, statement: str, parameters: tuple[Any, ...]) -> SpyResult:
        self.calls.append((statement, parameters))
        return self.result

    def __enter__(self) -> SpyConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _SpyEngine:
    def __init__(self, connection: SpyConnection) -> None:
        self._connection = connection

    def connect(self) -> SpyConnection:
        return self._connection


class _SpyRegistry:
    def __init__(self, connection: SpyConnection) -> None:
        self.connection = connection

    async def run(self, alias: str, database: str | None, operation: Callable[[Any], Any]) -> Any:
        return operation(_SpyEngine(self.connection))


def spy_service(connection: SpyConnection) -> DatabaseService:
    return DatabaseService(
        app_config(),
        cast(EngineRegistry, _SpyRegistry(connection)),
        catalog_factory=lambda *_: Catalog(),
    )


# --- valid restricted query generator ------------------------------------------------------------

USERS_COLUMNS = ["u.Id", "u.Email", "u.Phone", "u.Name"]
ORDERS_COLUMNS = ["o.Id", "o.UserId", "o.Total"]
PROTECTED = {"u.Email", "u.Phone", "o.Total"}
NUMERIC = {"u.Id", "o.Id", "o.UserId"}
PLAIN_TEXT = {"u.Name"}
FORBIDDEN_MUTATIONS: list[Callable[[str], str]] = [
    lambda s: s + " UNION SELECT 1",
    lambda s: s + "; DROP TABLE Canary",
    lambda s: s + " OPTION (MAXDOP 1)",
    lambda s: s + " FOR JSON AUTO",
    lambda s: s.replace("Users u", "Users u WITH (NOLOCK)", 1),
    lambda s: s.replace("Users u", "other.dbo.Users u", 1),
    lambda s: s.replace("Users u", "(SELECT Id FROM Users) u", 1),
    lambda s: s.replace("FROM", "INTO #t FROM", 1),
    lambda s: s.replace("SELECT", "SELECT DISTINCT", 1),
    lambda s: s.replace("SELECT", "SELECT LOWER('x'),", 1),
    lambda s: s.replace("SELECT", "SELECT (SELECT 1),", 1),
    lambda s: s.replace("SELECT", "SELECT @@version,", 1),
    lambda s: s.replace("SELECT", "SELECT CASE WHEN 1 = 1 THEN 1 END,", 1),
    lambda s: s.replace("SELECT", "WITH c AS (SELECT 1 AS n) SELECT", 1),
    lambda s: "EXEC ('" + s.replace("'", "''") + "')",
    lambda s: s + " CROSS APPLY dbo.F(1) f",
    lambda s: s.replace("SELECT", "SELECT SUM(u.Id),", 1),
    lambda s: "DELETE FROM Canary; " + s,
    lambda s: s.replace("FROM Users u", "FROM Users u, Orders x", 1),
]


@dataclass(frozen=True, slots=True)
class Spec:
    join: bool
    top: int | None
    projections: tuple[tuple[str, int | None], ...]
    predicates: tuple[tuple[Any, ...], ...]
    connectors: tuple[str, ...]
    parens: tuple[bool, ...]
    order: tuple[tuple[str, bool], ...]


_TEXT = st.text(max_size=24)
_PLAIN_LITERAL = st.text(alphabet="abcXYZ 09", max_size=6)


@st.composite
def specs(draw: st.DrawFn) -> Spec:
    join = draw(st.booleans())
    columns = USERS_COLUMNS + (ORDERS_COLUMNS if join else [])
    plain_numeric = sorted(NUMERIC & set(columns))
    protected = sorted(PROTECTED & set(columns))
    projections = []
    for _ in range(draw(st.integers(1, 4))):
        kind = draw(st.sampled_from(["column", "column", "column", "literal", "count"]))
        if kind == "column":
            text = draw(st.sampled_from(columns))
        elif kind == "literal":
            text = draw(st.sampled_from(["1", "'x'", "NULL", "-5"]))
        else:
            text = "COUNT(*)"
        projections.append((text, draw(st.one_of(st.none(), st.integers(0, 5)))))
    predicates: list[tuple[Any, ...]] = []
    for _ in range(draw(st.integers(0, 3))):
        kind = draw(st.sampled_from(["cmp", "in", "isnull", "token_eq", "token_in"]))
        if kind == "cmp":
            column = draw(st.sampled_from([*plain_numeric, "u.Name"]))
            op = draw(st.sampled_from(["=", "<>", "!=", "<", "<=", ">", ">="]))
            value = draw(st.integers(-5, 99)) if column in NUMERIC else draw(_PLAIN_LITERAL)
            predicates.append((kind, column, op, value))
        elif kind == "in":
            column = draw(st.sampled_from([*plain_numeric, "u.Name"]))
            values = draw(
                st.lists(
                    st.integers(-5, 99) if column in NUMERIC else _PLAIN_LITERAL,
                    min_size=1,
                    max_size=4,
                )
            )
            predicates.append((kind, column, tuple(values)))
        elif kind == "isnull":
            predicates.append((kind, draw(st.sampled_from([*plain_numeric, "u.Name"]))))
        elif kind == "token_eq":
            predicates.append((kind, draw(st.sampled_from(protected)), draw(_TEXT)))
        else:
            values = draw(st.lists(_TEXT, min_size=1, max_size=3))
            predicates.append((kind, draw(st.sampled_from(protected)), tuple(values)))
    count = len(predicates)
    connectors = tuple(draw(st.sampled_from(["AND", "OR"])) for _ in range(max(count - 1, 0)))
    parens = tuple(draw(st.booleans()) for _ in range(count))
    orderable = sorted(set(columns) - PROTECTED)
    order = tuple(
        (draw(st.sampled_from(orderable)), draw(st.booleans()))
        for _ in range(draw(st.integers(0, 2)))
    )
    top = draw(st.one_of(st.none(), st.integers(0, 50)))
    return Spec(join, top, tuple(projections), tuple(predicates), connectors, parens, order)


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render(spec: Spec, seed: int, alias_style: int = 0, token_codec: TokenCodec = OWN) -> str:
    """Render a spec with random whitespace, comments, and keyword case (deterministic in seed)."""
    rnd = random.Random(seed)

    def ws() -> str:
        return rnd.choice([" ", "  ", "\n", "\t", " /*c*/ ", " --c\n"])

    def kw(word: str) -> str:
        return rnd.choice([word.upper(), word.lower(), word.capitalize()])

    def token(value: str) -> str:
        issued = token_codec.encrypt(value)
        return "'" + str(issued) + "'"

    def literal(value: object) -> str:
        return str(value) if isinstance(value, int) else _sql_string(str(value))

    def predicate(item: tuple[Any, ...]) -> str:
        kind = item[0]
        if kind == "cmp":
            return f"{item[1]}{ws()}{item[2]}{ws()}{literal(item[3])}"
        if kind == "in":
            values = f",{ws()}".join(literal(v) for v in item[2])
            return f"{item[1]}{ws()}{kw('in')}{ws()}({ws()}{values}{ws()})"
        if kind == "isnull":
            return f"{item[1]}{ws()}{kw('is')}{ws()}{kw('null')}"
        if kind == "token_eq":
            return f"{item[1]}{ws()}={ws()}{token(item[2])}"
        values = f",{ws()}".join(token(v) for v in item[2])
        return f"{item[1]}{ws()}{kw('in')}{ws()}({ws()}{values}{ws()})"

    names = ["a", "Z_"][alias_style]
    parts = [kw("select"), ws()]
    if spec.top is not None:
        parts += [kw("top"), ws(), str(spec.top), ws()]
    rendered = []
    for text, alias in spec.projections:
        item = text
        if alias is not None:
            item += f"{ws()}{kw('as')}{ws()}{names}{alias}"
        rendered.append(item)
    parts.append(f",{ws()}".join(rendered))
    parts += [ws(), kw("from"), ws(), "Users", ws(), "u"]
    if spec.join:
        parts += [ws(), kw("join"), ws(), "Orders", ws(), "o", ws(), kw("on"), ws()]
        parts.append(f"o.UserId{ws()}={ws()}u.Id")
    if spec.predicates:
        parts += [ws(), kw("where"), ws()]
        for index, item in enumerate(spec.predicates):
            text = predicate(item)
            if spec.parens[index]:
                text = f"({ws()}{text}{ws()})"
            if index:
                parts += [ws(), kw(spec.connectors[index - 1]), ws()]
            parts.append(text)
    if spec.order:
        parts += [ws(), kw("order"), " ", kw("by"), ws()]  # sqlglot rejects ORDER /*c*/ BY
        keys = [col + (f"{ws()}{kw('desc')}" if desc else "") for col, desc in spec.order]
        parts.append(f",{ws()}".join(keys))
    return "".join(parts)
