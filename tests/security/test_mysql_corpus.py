"""MySQL/MariaDB adversarial corpus, plus the shared T-SQL corpus replayed on the mysql dialect.

Every case must fail with its expected error code and must never reach the database sink.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from corpus_support import MYSQL_CORPUS, TokenSources, expand, load_cases
from support import FOREIGN, OTHER_KEY, OWN, SpyConnection
from support_mysql import spy_mysql_service

from sql_mini_mcp.errors import DomainError, ErrorCode
from sql_mini_mcp.security.tokens import PREFIX, TokenCodec
from sql_mini_mcp.service import DatabaseService

TOKENS = TokenSources(OWN, FOREIGN, TokenCodec("srv", OTHER_KEY))
MYSQL_CASES = load_cases(MYSQL_CORPUS)
SHARED_CASES = load_cases()
ENGINES = ["mysql", "mariadb"]
# T-SQL corpus cases whose premise does not hold in MySQL: comments do not nest, '#' starts a
# comment, and "..." is a string literal. They are valid MySQL and stay one safe literal or
# stripped comment; test_mysql_dialect.py asserts that.
TSQL_ONLY = {
    "syntax::nested comment leaks into generated sql",
    "syntax::mysql style comment",
    "syntax::double quoted identifier breakout",
}
REPLAYED_CASES = [(case_id, case) for case_id, case in SHARED_CASES if case_id not in TSQL_ONLY]


def _harness(engine: str) -> tuple[DatabaseService, SpyConnection]:
    connection = SpyConnection()
    return spy_mysql_service(connection, engine), connection


def _assert_rejected(engine: str, case_id: str, case: dict[str, Any]) -> None:
    service, connection = _harness(engine)
    sql = expand(case["sql"], TOKENS)
    expected = ErrorCode(case.get("code", "QUERY_REJECTED"))
    with pytest.raises(DomainError) as info:
        asyncio.run(service.execute_sql("srv", "app", sql))
    assert info.value.code is expected, f"{case_id}: {info.value}"
    assert connection.calls == [], f"{case_id}: reached the database sink"
    message = str(info.value)
    assert PREFIX not in message
    assert len(message) < 400


def test_mysql_corpus_is_well_formed() -> None:
    ids = [case_id for case_id, _ in MYSQL_CASES]
    assert len(ids) == len(set(ids)), "duplicate corpus case names"
    assert len(MYSQL_CASES) >= 120
    codes = {member.value for member in ErrorCode}
    for case_id, case in MYSQL_CASES:
        assert case.get("reason"), case_id
        assert isinstance(case["sql"], str), case_id
        assert case.get("code", "QUERY_REJECTED") in codes, case_id
        assert set(case) <= {"name", "sql", "code", "reason"}, case_id


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    ("case_id", "case"), MYSQL_CASES, ids=[case_id for case_id, _ in MYSQL_CASES]
)
def test_mysql_corpus_case_is_rejected_without_reaching_the_database(
    engine: str, case_id: str, case: dict[str, Any]
) -> None:
    _assert_rejected(engine, case_id, case)


def test_tsql_only_exclusions_exist() -> None:
    assert {case_id for case_id, _ in SHARED_CASES} >= TSQL_ONLY


@pytest.mark.parametrize(
    ("case_id", "case"), REPLAYED_CASES, ids=[case_id for case_id, _ in REPLAYED_CASES]
)
def test_shared_corpus_case_is_rejected_on_the_mysql_dialect(
    case_id: str, case: dict[str, Any]
) -> None:
    _assert_rejected("mysql", case_id, case)
