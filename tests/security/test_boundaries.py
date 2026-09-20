"""Targeted tests for boundaries that mutation testing showed were under-specified."""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from typing import Any

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlglot import exp
from support import KEY, OWN, RUNTIME, Catalog, SpyConnection, SpyResult, validate

import sql_mini_mcp.security.schema as schema_module
import sql_mini_mcp.security.validated_query as vq_module
from sql_mini_mcp.config import PiiConfig, PiiRule
from sql_mini_mcp.errors import DomainError, ErrorCode
from sql_mini_mcp.security.executor import execute_validated
from sql_mini_mcp.security.lineage import _cross_check, analyze_query
from sql_mini_mcp.security.parser import (
    ParserLimits,
    parse_select,
    strip_comments,
    validate_allowlist,
)
from sql_mini_mcp.security.policy import PiiPolicy, PolicyDecision
from sql_mini_mcp.security.reasons import Reason
from sql_mini_mcp.security.schema import (
    ReflectedCatalog,
    SchemaCache,
    TableSchema,
    resolve_tables,
)
from sql_mini_mcp.security.tokens import TokenCodec
from sql_mini_mcp.security.validated_query import issue_validated_query

LIMITS = ParserLimits.from_runtime(RUNTIME)


def analyzed(sql: str):
    query = parse_select(sql, LIMITS)
    return analyze_query(query, resolve_tables(query, Catalog()), LIMITS)


# --- validated query ---------------------------------------------------------------------------


def test_output_plan_and_policy_must_have_the_same_length() -> None:
    result = analyzed("SELECT Id, Name FROM Users")
    with pytest.raises(ValueError, match="zip"):
        issue_validated_query(
            result,
            PolicyDecision((False,), ()),
            alias="srv",
            database="app",
            max_rows=5,
            runtime=RUNTIME,
            limits=LIMITS,
        )


def test_a_literal_that_looks_like_a_bind_marker_is_rejected_not_reordered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vq_module.secrets, "token_hex", lambda _n=None: "0" * 16)
    token = OWN.encrypt("value")
    sql = f"SELECT Id FROM Users WHERE Name = '__bind_{'0' * 16}_0__' AND Email = '{token}'"
    with pytest.raises(DomainError) as info:
        validate(sql)
    assert info.value.public_message == f"Query rejected: {Reason.BIND_UNSAFE.value}."


def test_marker_text_for_a_missing_nonce_is_just_a_literal() -> None:
    token = OWN.encrypt("value")
    query = validate(f"SELECT Id FROM Users WHERE Name = '__bind_None_0__' AND Email = '{token}'")
    assert query.parameters == ("value",)
    assert "'__bind_None_0__'" in query.sql


def test_bind_markers_use_a_fresh_random_nonce_each_time(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    real = vq_module.secrets.token_hex

    def spy(nbytes: int | None = None) -> str:
        seen.append(-1 if nbytes is None else nbytes)
        return real(nbytes)

    monkeypatch.setattr(vq_module.secrets, "token_hex", spy)
    validate(f"SELECT Id FROM Users WHERE Email = '{OWN.encrypt('a')}'")
    assert seen == [8]


# --- executor ----------------------------------------------------------------------------------


def test_rows_must_match_the_output_plan_width() -> None:
    query = validate("SELECT Id FROM Users")
    connection = SpyConnection(SpyResult(["Id"], [(1, 2)]))
    with pytest.raises(ValueError, match="zip"):
        execute_validated(connection, query, OWN)


# --- tokens ------------------------------------------------------------------------------------


def _forge(payload: dict[str, Any] | bytes) -> str:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    nonce = bytes(12)
    sealed = AESGCM(KEY).encrypt(nonce, body, b"pii:v1\x00srv")
    return "pii:v1:" + base64.urlsafe_b64encode(nonce + sealed).decode().rstrip("=")


@pytest.mark.parametrize(
    ("tag", "data"),
    [
        ("decimal", "NaN"),
        ("decimal", "Infinity"),
        ("decimal", "1.50e0"),
        ("decimal", " 1"),
        ("date", "20240229"),
        ("time", "010203"),
        ("datetime", "2024-02-29 13:14:15"),
        ("uuid", "12345678123456781234567812345678"),
        ("uuid", "{12345678-1234-5678-1234-567812345678}"),
        ("bytes", "AP8"),
        ("bytes", "AP8=\n"),
        ("float", 1),
        ("int", 1.0),
        ("bool", 0),
        ("str", 1),
    ],
)
def test_forged_non_canonical_payloads_are_rejected(tag: str, data: Any) -> None:
    token = _forge({"v": 1, "t": tag, "d": data})
    with pytest.raises(DomainError) as info:
        OWN.decrypt(token)
    assert info.value.code is ErrorCode.INVALID_PII_TOKEN


def test_forged_canonical_payloads_round_trip() -> None:
    assert OWN.decrypt(_forge({"v": 1, "t": "decimal", "d": "1.50"})) == OWN.decrypt(
        OWN.encrypt(__import__("decimal").Decimal("1.50"))
    )


def test_a_bool_is_not_accepted_as_a_version_number() -> None:
    with pytest.raises(DomainError):
        OWN.decrypt(_forge({"v": True, "t": "str", "d": "x"}))


def test_short_ciphertext_and_empty_input_are_invalid() -> None:
    codec = TokenCodec("srv", KEY)
    for candidate in ("pii:v1:" + "A" * 27, "pii:v1:" + "A" * 43, ""):
        with pytest.raises(DomainError):
            codec.decrypt(candidate)


# --- schema cache and catalog ------------------------------------------------------------------


def test_cache_entry_expires_exactly_at_the_ttl() -> None:
    now = [0.0]
    cache = SchemaCache(4, 10.0, clock=lambda: now[0])
    cache.put("k", ("v",))
    now[0] = 10.0
    assert cache.get("k") is None


def test_cache_recency_is_refreshed_by_reads_and_overwrites() -> None:
    cache = SchemaCache(2, 1000.0)
    cache.put("a", (1,))
    cache.put("b", (2,))
    cache.put("a", (3,))
    cache.put("c", (4,))
    assert cache.get("b") is None
    assert cache.get("a") == (3,)


class StubInspector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def get_columns(self, table: str, schema: str | None = None) -> list[dict[str, str]]:
        self.calls.append((table, schema))
        return [{"name": f"{schema}.{table}.c"}]


def test_columns_are_reflected_per_schema_and_cached_per_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = StubInspector()
    monkeypatch.setattr(schema_module, "inspect", lambda _connection: inspector)
    catalog = ReflectedCatalog(
        sa.create_engine("sqlite://").connect(), SchemaCache(8, 60), "a", "d"
    )
    assert catalog.columns("sales", "Items") == ("sales.Items.c",)
    assert catalog.columns("dbo", "Items") == ("dbo.Items.c",)
    assert catalog.columns("sales", "Items") == ("sales.Items.c",)
    assert catalog.columns("sales", "Other") == ("sales.Other.c",)
    assert inspector.calls == [("Items", "sales"), ("Items", "dbo"), ("Other", "sales")]


def test_an_empty_schema_is_reflected_as_the_default_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = StubInspector()
    monkeypatch.setattr(schema_module, "inspect", lambda _connection: inspector)
    catalog = ReflectedCatalog(
        sa.create_engine("sqlite://").connect(), SchemaCache(8, 60), "a", "d"
    )
    catalog.columns("", "T")
    assert inspector.calls == [("T", None)]


def test_resolved_schema_and_table_identifiers_are_quoted() -> None:
    query = parse_select("SELECT Id FROM dbo.Users", LIMITS)
    resolve_tables(query, Catalog())
    table = query.find(exp.Table)
    assert table is not None
    assert table.args["db"].args["quoted"] is True
    assert table.this.args["quoted"] is True


def test_a_catalog_qualified_table_node_is_rejected_by_resolution() -> None:
    query = parse_select("SELECT Id FROM Users", LIMITS)
    table = query.find(exp.Table)
    assert table is not None
    table.set("catalog", exp.to_identifier("other"))
    with pytest.raises(DomainError) as info:
        resolve_tables(query, Catalog())
    assert info.value.public_message == f"Query rejected: {Reason.TABLE_SCOPE.value}."


def test_a_non_identifier_table_name_is_rejected_by_resolution() -> None:
    query = parse_select("SELECT Id FROM Users", LIMITS)
    table = query.find(exp.Table)
    assert table is not None
    table.set("this", exp.Var(this="Users"))
    with pytest.raises(DomainError) as info:
        resolve_tables(query, Catalog())
    assert info.value.public_message == f"Query rejected: {Reason.TABLE_SCOPE.value}."


def test_a_vanished_table_is_rejected_when_its_columns_are_loaded() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        catalog = ReflectedCatalog(connection, SchemaCache(8, 60), "a", "d")
        with pytest.raises(DomainError) as info:
            catalog.columns("main", "Gone")
    assert info.value.public_message == f"Query rejected: {Reason.TABLE_GONE.value}."


def test_two_case_variants_of_a_table_are_ambiguous() -> None:
    class Twin(Catalog):
        tables = {("dbo", "Users"): ["Id"], ("dbo", "USERS"): ["Id"]}  # noqa: RUF012

    query = parse_select("SELECT Id FROM dbo.users", LIMITS)
    with pytest.raises(DomainError):
        resolve_tables(query, Twin())


# --- lineage -----------------------------------------------------------------------------------


def _tables(*tables: TableSchema) -> Sequence[TableSchema]:
    return tables


USERS = TableSchema("dbo", "Users", ("Id", "Name"))
ORDERS = TableSchema("dbo", "Orders", ("Id", "UserId"))


def test_the_cross_check_accepts_a_fully_resolved_query() -> None:
    query = parse_select("SELECT [Users].[Id] FROM [dbo].[Users]", LIMITS)
    _cross_check(query, _tables(USERS))


def test_the_cross_check_rejects_an_unknown_column() -> None:
    query = parse_select("SELECT [Users].[Nope] FROM [dbo].[Users]", LIMITS)
    with pytest.raises(DomainError) as info:
        _cross_check(query, _tables(USERS))
    assert info.value.public_message == f"Query rejected: {Reason.QUALIFY_FAILED.value}."


def test_the_cross_check_rejects_a_column_with_the_wrong_case() -> None:
    query = parse_select("SELECT [Users].[id] FROM [dbo].[Users]", LIMITS)
    with pytest.raises(DomainError):
        _cross_check(query, _tables(USERS))


def test_the_cross_check_rejects_an_ambiguous_unqualified_column() -> None:
    query = parse_select(
        "SELECT Id FROM [dbo].[Users] JOIN [dbo].[Orders] ON [Orders].[UserId] = [Users].[Id]",
        LIMITS,
    )
    with pytest.raises(DomainError):
        _cross_check(query, _tables(USERS, ORDERS))


# --- policy ------------------------------------------------------------------------------------


def _decision(rules: list[PiiRule], sql: str, database: str = "app") -> tuple[bool, ...]:
    return PiiPolicy(database, PiiConfig(rules=rules), OWN).evaluate(analyzed(sql)).protected


def test_a_later_rule_still_applies_after_non_matching_rules() -> None:
    other_db = PiiRule(database="elsewhere", schema="dbo", table="Users", columns=["Name"])
    other_schema = PiiRule(database="*", schema="sales", table="Users", columns=["Name"])
    other_table = PiiRule(database="*", schema="dbo", table="Orders", columns=["Name"])
    other_column = PiiRule(database="*", schema="dbo", table="Users", columns=["Phone"])
    match = PiiRule(database="app", schema="dbo", table="Users", columns=["Name"])
    rules = [other_db, other_schema, other_table, other_column, match]
    assert _decision(rules, "SELECT Id, Name FROM Users") == (False, True)
    assert _decision(rules[:-1], "SELECT Id, Name FROM Users") == (False, False)


def test_a_rule_matches_only_its_own_database_schema_table_and_column() -> None:
    rule = PiiRule(database="app", schema="dbo", table="Users", columns=["Name"])
    assert _decision([rule], "SELECT Name FROM Users", "app") == (True,)
    assert _decision([rule], "SELECT Name FROM Users", "APP") == (True,)
    assert _decision([rule], "SELECT Name FROM Users", "other") == (False,)
    assert _decision([rule], "SELECT Id FROM Users", "app") == (False,)
    assert _decision([rule], "SELECT Id FROM Orders", "app") == (False,)


def test_a_wildcard_rule_column_list_is_case_insensitive() -> None:
    rule = PiiRule(database="*", table="users", columns=["NAME", "id"])
    assert _decision([rule], "SELECT Id, Name FROM Users") == (True, True)


# --- parser ------------------------------------------------------------------------------------


def test_a_hand_built_temp_table_name_is_rejected_by_the_allowlist() -> None:
    for name in ("#t", "@t", "##t"):
        query = exp.select("Id").from_(exp.Table(this=exp.to_identifier(name, quoted=True)))
        with pytest.raises(DomainError) as info:
            validate_allowlist(query)
        assert info.value.public_message == f"Query rejected: {Reason.TABLE_UNSUPPORTED.value}."


def test_strip_comments_clears_every_node_but_keeps_the_tree() -> None:
    query = exp.select("Id").from_("Users")
    for node in query.walk():
        node.add_comments(["c"])
    strip_comments(query)
    assert all(not node.comments for node in query.walk())
    assert query.sql("tsql") == "SELECT Id FROM Users"


def test_generated_sql_never_carries_comments() -> None:
    sql = "/* a */ SELECT /* b */ Id -- c\nFROM Users /* d */"
    assert "/*" not in validate(sql).sql
    assert "--" not in validate(sql).sql
