import pytest
from sqlglot import exp

import sql_safe_mcp.security.parser as parser_module
from sql_safe_mcp.config import RuntimeConfig
from sql_safe_mcp.errors import DomainError, ErrorCode
from sql_safe_mcp.security.parser import ParserLimits, parse_select

LIMITS = ParserLimits(max_sql_chars=256, max_ast_nodes=50, max_joins=2, max_in_list_items=3)


def rejected(sql: str, limits: ParserLimits = LIMITS) -> DomainError:
    with pytest.raises(DomainError) as info:
        parse_select(sql, limits)
    assert info.value.code is ErrorCode.QUERY_REJECTED
    return info.value


def test_limits_come_from_runtime_config() -> None:
    runtime = RuntimeConfig(max_sql_chars=300, max_ast_nodes=40, max_joins=1, max_in_list_items=7)
    assert ParserLimits.from_runtime(runtime) == ParserLimits(300, 40, 1, 7)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select a from t",
        "SELECT 1;",
        "SELECT 1 /* c */",
        "-- c\nSELECT 1",
        "SELECT 1;;",
    ],
)
def test_accepts_single_select(sql: str) -> None:
    assert isinstance(parse_select(sql, LIMITS), exp.Select)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   \n\t",
        "-- only a comment",
        "/* only a comment */",
        ";",
        "SELECT 1; SELECT 2",
        "SELECT 1; DROP TABLE t",
        "SELECT 1 /**/;DROP TABLE t",
        "SELECT 1 UNION SELECT 2",
        "(SELECT 1)",
        "DELETE FROM t",
        "EXEC sp_who",
        "SELECT (",
        "SELECT 'unterminated",
        "\x00\ud800",
    ],
)
def test_rejects_non_single_select(sql: str) -> None:
    rejected(sql)


def test_char_limit_boundary() -> None:
    limits = ParserLimits(20, 1000, 2, 3)
    exact = "SELECT 1" + " " * 12
    assert len(exact) == 20
    parse_select(exact, limits)
    rejected(exact + " ", limits)


def test_char_limit_checked_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("parser was called")

    monkeypatch.setattr(parser_module.sqlglot, "parse", fail)
    rejected("SELECT 1" + " " * 300)


def test_node_limit_boundary() -> None:
    sql = "SELECT a FROM t WHERE a = 1"
    count = len(list(parse_select(sql, LIMITS).walk()))
    parse_select(sql, ParserLimits(256, count, 2, 3))
    rejected(sql, ParserLimits(256, count - 1, 2, 3))


def test_join_limit_boundary() -> None:
    def joins(n: int) -> str:
        return "SELECT 1 FROM a " + " ".join(f"JOIN b{i} ON 1 = 1" for i in range(n))

    parse_select(joins(2), LIMITS)
    rejected(joins(3), LIMITS)


def test_in_list_limit_boundary() -> None:
    parse_select("SELECT 1 FROM t WHERE a IN (1, 2, 3)", LIMITS)
    rejected("SELECT 1 FROM t WHERE a IN (1, 2, 3, 4)", LIMITS)


def test_in_list_limit_applies_to_every_in() -> None:
    rejected("SELECT 1 FROM t WHERE a IN (1) AND b IN (1, 2, 3, 4)", LIMITS)


def test_unexpected_parser_error_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RecursionError("secret detail")

    monkeypatch.setattr(parser_module.sqlglot, "parse", boom)
    error = rejected("SELECT 1")
    assert "secret detail" not in str(error)


def test_deeply_nested_input_is_rejected_not_crashed() -> None:
    limits = ParserLimits(100_000, 2000, 2, 3)
    rejected("SELECT " + "(" * 5000 + "1" + ")" * 5000, limits)


@pytest.mark.parametrize(
    "sql",
    ["SELECT \u202e\x00", "SELECT '\x00' AS \"\U0001f600\"", "\ufeffSELECT 1"],
)
def test_arbitrary_unicode_never_raises_unexpected_errors(sql: str) -> None:
    try:
        parse_select(sql, LIMITS)
    except DomainError as error:
        assert error.code is ErrorCode.QUERY_REJECTED
